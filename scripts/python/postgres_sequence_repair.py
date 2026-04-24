"""
Realign PostgreSQL SERIAL sequences to MAX(id) after restore or migration with explicit IDs.

Fixes errors such as: duplicate key value violates unique constraint "jobs_pkey".

Usage (from repo root, WSL + venv with psycopg2 as for the migrate script):
  python scripts/python/postgres_sequence_repair.py

Options mirror migrate script PG flags; defaults come from config.json / env.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Discovered at runtime from pg_depend — see _discover_serial_columns().
# A hand-maintained list was previously used here but silently drifted: file_paths
# and several other tables were missing, so their sequences were never advanced
# after Firebird→Postgres migration (which inserts with explicit IDs), causing
# duplicate-key errors on the first runtime INSERT.
_DISCOVER_SEQ_COLUMNS_SQL = """
SELECT t.relname AS tbl, a.attname AS col
FROM pg_class s
JOIN pg_depend d   ON d.objid = s.oid AND d.classid = 'pg_class'::regclass
JOIN pg_class t    ON d.refobjid = t.oid
JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
WHERE s.relkind = 'S'
  AND t.relkind = 'r'
  AND t.relnamespace IN (
        SELECT oid FROM pg_namespace
        WHERE nspname = ANY (current_schemas(false))
      )
ORDER BY t.relname, a.attnum
"""


def _discover_serial_columns(pg_conn):
    """Return [(table, column), ...] for every SERIAL/owned-sequence column in the current schema."""
    cur = pg_conn.cursor()
    try:
        cur.execute(_DISCOVER_SEQ_COLUMNS_SQL)
        return [(row[0], row[1]) for row in cur.fetchall()]
    finally:
        cur.close()


def reset_sequences(pg_conn) -> None:
    """Reset every owned SERIAL sequence to MAX(pk); next insert gets MAX(pk)+1.

    Autodiscovers columns via pg_depend so new tables don't need manual registration.
    """
    targets = _discover_serial_columns(pg_conn)
    if not targets:
        logger.warning("No owned sequences discovered — nothing to reset.")
        return
    pg_cur = pg_conn.cursor()
    try:
        for table, id_col in targets:
            try:
                pg_cur.execute(f'SELECT MAX("{id_col}") FROM "{table}"')
                row = pg_cur.fetchone()
                max_id = row[0] if row and row[0] is not None else 0
                pg_cur.execute(
                    "SELECT setval(pg_get_serial_sequence(%s, %s), %s, true)",
                    (table, id_col, max(max_id, 1)),
                )
                logger.info("  Reset sequence for %s.%s → next id after %s", table, id_col, max_id)
            except Exception as e:
                logger.warning("  Could not reset sequence for %s.%s: %s", table, id_col, e)
                pg_conn.rollback()
        pg_conn.commit()
    finally:
        pg_cur.close()


def _resolve_postgres_config(db_cfg, env, args):
    postgres_cfg = db_cfg.get("postgres", {}) or {}
    pg_host = (
        getattr(args, "pg_host", None)
        or env.get("POSTGRES_HOST")
        or postgres_cfg.get("host")
        or db_cfg.get("host")
        or "localhost"
    )
    pg_port = int(
        getattr(args, "pg_port", None)
        or env.get("POSTGRES_PORT")
        or postgres_cfg.get("port")
        or db_cfg.get("port")
        or 5432
    )
    pg_db = (
        getattr(args, "pg_db", None)
        or env.get("POSTGRES_DB")
        or postgres_cfg.get("database")
        or db_cfg.get("database")
        or "image_scoring"
    )
    pg_user = (
        getattr(args, "pg_user", None)
        or env.get("POSTGRES_USER")
        or postgres_cfg.get("user")
        or db_cfg.get("user")
        or "postgres"
    )
    pg_password = (
        getattr(args, "pg_password", None)
        or env.get("POSTGRES_PASSWORD")
        or postgres_cfg.get("password")
        or db_cfg.get("password")
        or "postgres"
    )
    return pg_host, pg_port, pg_db, pg_user, pg_password


def _get_pg_conn(host, port, database, user, password):
    import psycopg2

    return psycopg2.connect(
        host=host,
        port=port,
        dbname=database,
        user=user,
        password=password,
    )


def main():
    parser = argparse.ArgumentParser(description="Repair PostgreSQL SERIAL sequences after restore/import")
    parser.add_argument("--pg-host", default=None)
    parser.add_argument("--pg-port", default=None, type=int)
    parser.add_argument("--pg-db", default=None)
    parser.add_argument("--pg-user", default=None)
    parser.add_argument("--pg-password", default=None)
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(project_root))
    from modules import config as app_config

    db_cfg = app_config.get_config_section("database")
    host, port, db, user, password = _resolve_postgres_config(db_cfg, os.environ, args)
    logger.info("PostgreSQL: %s:%s/%s (user=%s)", host, port, db, user)

    conn = _get_pg_conn(host, port, db, user, password)
    try:
        logger.info("Resetting sequences (autodiscovered from pg_depend)…")
        reset_sequences(conn)
        logger.info("Done.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
