"""
One-time migration script: Firebird SQL → PostgreSQL

Reads all data from an existing Firebird .fdb file and inserts it into
the PostgreSQL database configured in config.json / environment variables.

Prerequisites:
  - firebird-driver must be installed (pip install firebird-driver)
  - PostgreSQL must be running with the musiq database created
  - pgvector extension must be enabled (run: CREATE EXTENSION vector;)
  - The target PostgreSQL schema must already exist (run: python launch.py --init-db-only)

Usage:
  python scripts/python/migrate_firebird_to_postgres.py [options]

Options:
  --fdb-path PATH       Path to the Firebird .fdb file (default: scoring_history.fdb)
  --fdb-user USER       Firebird username (default: sysdba)
  --fdb-password PASS   Firebird password (default: masterkey)
  --batch-size N        Rows per batch (default: 500)
  --skip-table TABLE    Skip a specific table (can be repeated)
  --clear-target        Clear selected target tables before migration
  --dry-run             Print counts without inserting
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import numpy as np
import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from postgres_sequence_repair import reset_sequences

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Tables to migrate, in FK dependency order (parents before children)
TABLES_ORDER = [
    "jobs",
    "folders",
    "stacks",
    "images",
    "file_paths",
    "job_phases",       # depends on jobs
    "job_steps",        # depends on jobs
    "image_exif",
    "image_xmp",
    "cluster_progress",
    "culling_sessions",
    "culling_picks",
    "pipeline_phases",
    "image_phase_status",
    "stack_cache",      # depends on stacks + images + folders
    "keywords_dim",
    "image_keywords",
]


def get_tables_for_validation():
    """
    Tables to compare in validate_migration (full active pipeline set).

    Intentionally ignores --skip-table so a partial migration cannot report success
    when Firebird and Postgres counts still differ on skipped tables.
    """
    return TABLES_ORDER


def get_pg_conn(host, port, dbname, user, password):
    conn = psycopg2.connect(
        host=host, port=port, dbname=dbname, user=user, password=password,
        options="-c client_encoding=UTF8",
    )
    conn.autocommit = False
    register_vector(conn)
    return conn


def get_fb_conn(fdb_path, user, password):
    try:
        from firebird.driver import connect as fb_connect
        from firebird.driver import driver_config
    except ImportError:
        logger.error("firebird-driver not installed. Run: pip install firebird-driver")
        sys.exit(1)

    if os.name == "nt":
        # Ensure we have an absolute path to the project root
        project_root = Path(__file__).resolve().parent.parent.parent
        fb_dll = project_root / "Firebird" / "fbclient.dll"
        if fb_dll.exists():
            logger.info("  Found Firebird client DLL at %s", fb_dll)
            driver_config.fb_client_library.value = str(fb_dll)
        else:
            logger.warning("  Firebird client DLL not found at %s. Falling back to default search.", fb_dll)

    return fb_connect(str(fdb_path), user=user, password=password, charset="UTF8")


def get_fb_columns(fb_cur, table_name):
    """Return list of column names for a Firebird table (lowercased)."""
    fb_cur.execute(
        "SELECT RDB$FIELD_NAME FROM RDB$RELATION_FIELDS "
        "WHERE RDB$RELATION_NAME = ? ORDER BY RDB$FIELD_POSITION",
        (table_name.upper(),),
    )
    return [row[0].strip().lower() for row in fb_cur.fetchall()]


def get_pg_columns(pg_cur, table_name):
    """Return list of column names for a PostgreSQL table."""
    pg_cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position",
        (table_name.lower(),),
    )
    cols = []
    for row in pg_cur.fetchall():
        if hasattr(row, "keys"):
            cols.append(row["column_name"])
        else:
            cols.append(row[0])
    return cols


def table_exists_fb(fb_cur, table_name):
    fb_cur.execute(
        "SELECT 1 FROM RDB$RELATIONS WHERE RDB$RELATION_NAME = ? AND RDB$SYSTEM_FLAG = 0",
        (table_name.upper(),),
    )
    return fb_cur.fetchone() is not None


def table_exists_pg(pg_cur, table_name):
    pg_cur.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s",
        (table_name.lower(),),
    )
    return pg_cur.fetchone() is not None


def migrate_table(fb_conn, pg_conn, table_name, batch_size=500, dry_run=False):
    """Migrate a single table from Firebird to PostgreSQL."""
    fb_cur = fb_conn.cursor()
    pg_cur = pg_conn.cursor()

    try:
        if not table_exists_fb(fb_cur, table_name):
            logger.info("  Firebird table %s does not exist — skipping", table_name)
            return 0

        # Get column intersection (only migrate columns that exist in both)
        fb_cols = get_fb_columns(fb_cur, table_name)
        pg_cols = get_pg_columns(pg_cur, table_name)
        pg_cols_set = set(pg_cols)

        # Columns to migrate: present in Firebird AND PostgreSQL
        common_cols = [c for c in fb_cols if c in pg_cols_set]
        if not common_cols:
            logger.warning("  No common columns for %s — skipping", table_name)
            return 0

        # Check current PG row count
        pg_cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        existing_count = pg_cur.fetchone()[0]
        if existing_count > 0:
            logger.info("  PostgreSQL %s already has %d rows — skipping (pass --clear-target to clear before migration)", table_name, existing_count)
            return 0

        # Fetch all rows from Firebird
        fb_select_cols = ", ".join(common_cols)
        fb_cur.execute(f"SELECT {fb_select_cols} FROM {table_name}")

        is_embedding_table = table_name == "images"
        embedding_col_idx = common_cols.index("image_embedding") if (is_embedding_table and "image_embedding" in common_cols) else -1

        total_inserted = 0
        batch = []

        def flush_batch(batch):
            if not batch or dry_run:
                return
            placeholders = ", ".join(["%s"] * len(common_cols))
            insert_sql = (
                f"INSERT INTO {table_name} ({', '.join(common_cols)}) "
                f"VALUES ({placeholders}) ON CONFLICT DO NOTHING"
            )
            pg_cur.executemany(insert_sql, batch)
            pg_conn.commit()

        while True:
            rows = fb_cur.fetchmany(batch_size)
            if not rows:
                break

            for row in rows:
                converted = list(row)

                # Convert embedding: Firebird BLOB bytes → numpy array for pgvector
                if embedding_col_idx >= 0:
                    emb = converted[embedding_col_idx]
                    if emb is not None:
                        try:
                            emb_bytes = bytes(emb)
                            converted[embedding_col_idx] = np.frombuffer(emb_bytes, dtype=np.float32)
                        except Exception as e:
                            logger.warning("    Could not convert embedding for row: %s", e)
                            converted[embedding_col_idx] = None

                # Convert Firebird BLOBs and Booleans
                for i, val in enumerate(converted):
                    if isinstance(val, bool):
                        # Fix for smallint columns in Postgres rejecting bools
                        converted[i] = 1 if val else 0
                    elif hasattr(val, "read"):
                        try:
                            converted[i] = val.read()
                        except Exception:
                            converted[i] = None

                batch.append(tuple(converted))

            flush_batch(batch)
            total_inserted += len(batch)
            batch = []
            logger.info("  %s: %d rows migrated...", table_name, total_inserted)

        # Flush any remaining
        flush_batch(batch)
        total_inserted += len(batch)

        return total_inserted
    finally:
        fb_cur.close()
        pg_cur.close()


def clear_target_tables(pg_conn, tables):
    """Truncate all target tables in one statement, resetting sequences."""
    pg_cur = pg_conn.cursor()
    try:
        table_list = ", ".join(tables)
        logger.info("Truncating target tables: %s", table_list)
        pg_cur.execute(f"TRUNCATE {table_list} RESTART IDENTITY CASCADE")
        pg_conn.commit()
    finally:
        pg_cur.close()


def validate_migration(fb_conn, pg_conn, tables):
    """Compare row counts between Firebird and PostgreSQL for all tables."""
    fb_cur = fb_conn.cursor()
    pg_cur = pg_conn.cursor()
    try:
        all_match = True
        logger.info("Validating row counts:")
        for table in tables:
            if not table_exists_fb(fb_cur, table):
                continue
            fb_cur.execute(f"SELECT COUNT(*) FROM {table}")
            fb_count = fb_cur.fetchone()[0]

            pg_cur.execute(f"SELECT COUNT(*) FROM {table}")
            pg_count = pg_cur.fetchone()[0]

            status = "MATCH" if fb_count == pg_count else "MISMATCH"
            if fb_count != pg_count:
                all_match = False
            logger.info("  %s: FB=%d, PG=%d [%s]", table.ljust(20), fb_count, pg_count, status)

        return all_match
    finally:
        fb_cur.close()
        pg_cur.close()


def _resolve_postgres_config(db_cfg, env, args):
    """Resolve PostgreSQL settings with explicit precedence.

    Precedence:
      1) CLI args
      2) Environment variables
      3) database.postgres.*
      4) legacy database.* flat keys (temporary fallback with warning)
      5) hardcoded defaults
    """
    postgres_cfg = db_cfg.get("postgres", {}) or {}

    def _pick(cli_value, env_key, nested_key, legacy_key, default):
        if cli_value is not None:
            return cli_value
        if env.get(env_key) is not None:
            return env[env_key]
        if postgres_cfg.get(nested_key) is not None:
            return postgres_cfg[nested_key]
        if db_cfg.get(legacy_key) is not None:
            logger.warning(
                "Using legacy database.%s for PostgreSQL config fallback. "
                "Please migrate to database.postgres.%s.",
                legacy_key,
                nested_key,
            )
            return db_cfg[legacy_key]
        return default

    pg_host = _pick(args.pg_host, "POSTGRES_HOST", "host", "host", "localhost")
    pg_port = _pick(args.pg_port, "POSTGRES_PORT", "port", "port", 5432)
    pg_db = _pick(args.pg_db, "POSTGRES_DB", "dbname", "dbname", "musiq")
    pg_user = _pick(args.pg_user, "POSTGRES_USER", "user", "user", "musiq")
    pg_password = _pick(args.pg_password, "POSTGRES_PASSWORD", "password", "password", "musiq")

    try:
        pg_port = int(pg_port)
    except (TypeError, ValueError):
        logger.warning("Invalid PostgreSQL port %r; using default 5432", pg_port)
        pg_port = 5432

    return pg_host, pg_port, pg_db, pg_user, pg_password


def build_parser():
    parser = argparse.ArgumentParser(description="Migrate Firebird DB to PostgreSQL")
    parser.add_argument("--fdb-path", default=None, help="Path to Firebird .fdb file")
    parser.add_argument("--fdb-user", default="sysdba", help="Firebird username")
    parser.add_argument("--fdb-password", default=None, help="Firebird password")
    parser.add_argument("--pg-host", default=None, help="PostgreSQL host")
    parser.add_argument("--pg-port", default=None, type=int, help="PostgreSQL port")
    parser.add_argument("--pg-db", default=None, help="PostgreSQL database name")
    parser.add_argument("--pg-user", default=None, help="PostgreSQL username")
    parser.add_argument("--pg-password", default=None, help="PostgreSQL password")
    parser.add_argument("--batch-size", default=500, type=int, help="Rows per batch")
    parser.add_argument("--skip-table", action="append", default=[], help="Skip a table")
    parser.add_argument(
        "--clear-target",
        action="store_true",
        help="Clear selected target tables before migration",
    )
    parser.add_argument("--dry-run", action="store_true", help="Count rows without inserting")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    # Resolve paths from project root
    project_root = Path(__file__).parent.parent.parent

    # Load config
    sys.path.insert(0, str(project_root))
    from modules import config as app_config
    db_cfg = app_config.get_config_section("database")

    # Firebird settings
    fdb_path = args.fdb_path or project_root / db_cfg.get("filename", "scoring_history.fdb")
    fdb_user = args.fdb_user
    fdb_password = (
        args.fdb_password
        or os.environ.get("FIREBIRD_PASSWORD")
        or "masterkey"
    )

    # PostgreSQL settings
    pg_host, pg_port, pg_db, pg_user, pg_password = _resolve_postgres_config(
        db_cfg=db_cfg,
        env=os.environ,
        args=args,
    )

    logger.info("Firebird source: %s (user=%s)", fdb_path, fdb_user)
    logger.info("PostgreSQL target: %s:%d/%s (user=%s)", pg_host, pg_port, pg_db, pg_user)

    if not Path(fdb_path).exists():
        logger.error("Firebird file not found: %s", fdb_path)
        sys.exit(1)

    # Connect
    logger.info("Connecting to Firebird...")
    fb_conn = get_fb_conn(fdb_path, fdb_user, fdb_password)
    logger.info("Connecting to PostgreSQL...")
    pg_conn = get_pg_conn(pg_host, pg_port, pg_db, pg_user, pg_password)

    tables = [t for t in TABLES_ORDER if t not in args.skip_table]
    validation_tables = get_tables_for_validation()

    if args.dry_run:
        if args.clear_target:
            logger.info("DRY RUN — --clear-target ignored, no data will be modified")
        logger.info("DRY RUN — no data will be inserted")
        validate_migration(fb_conn, pg_conn, validation_tables)
        return

    if args.clear_target:
        logger.info("--clear-target enabled: clearing target tables before migration")
        clear_target_tables(pg_conn, tables)
    else:
        logger.info("--clear-target not provided: existing target data will be preserved; non-empty tables are skipped")

    role_cur = pg_conn.cursor()
    try:
        logger.info("Disabling foreign key checks (setting session_replication_role = replica)...")
        role_cur.execute("SET session_replication_role = 'replica'")
        role_cur.close()

        # Migrate each table
        total = 0
        try:
            for table in tables:
                logger.info("Migrating table: %s", table)
                count = migrate_table(fb_conn, pg_conn, table, args.batch_size, args.dry_run)
                logger.info("  %s: %d rows migrated", table, count)
                total += count
        except Exception as e:
            logger.error("Migration loop failed: %s", e)
            pg_conn.rollback() # Crucial: clears transaction error so finally can run SQL
            raise

        logger.info("Total rows migrated: %d", total)

        # Reset sequences
        logger.info("Resetting PostgreSQL sequences...")
        reset_sequences(pg_conn)

        # Validate
        all_ok = validate_migration(fb_conn, pg_conn, validation_tables)
        if all_ok:
            logger.info("\nMigration complete — all row counts match!")
        else:
            logger.warning("\nMigration complete with mismatches — review above")

    finally:
        logger.info("Restoring foreign key checks (setting session_replication_role = origin)...")
        # Use a fresh cursor or ensure previous one is usable
        restore_cur = pg_conn.cursor()
        try:
            restore_cur.execute("SET session_replication_role = 'origin'")
            pg_conn.commit()
        finally:
            restore_cur.close()

        fb_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    main()
