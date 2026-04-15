import logging
import os
import re
import sys
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool
from pgvector.psycopg2 import register_vector
import datetime
import json
from modules import config
from modules.test_db_constants import (
    POSTGRES_PRODUCTION_IN_PYTEST_ENV,
    POSTGRES_PRODUCTION_PYTEST_RISK_ACCEPTED_ENV,
    POSTGRES_TEST_DB,
    postgres_production_allowed_in_pytest,
)

logger = logging.getLogger(__name__)

_pool = None

_warned_production_pytest_incomplete = False


def _pytest_active() -> bool:
    return "pytest" in sys.modules or bool(os.environ.get("PYTEST_CURRENT_TEST"))


def _env_truthy(key: str) -> bool:
    return os.environ.get(key, "").strip().lower() in ("1", "true", "yes")


def get_pg_config():
    global _warned_production_pytest_incomplete
    db_config = config.get_config_section("database") or {}
    pg = db_config.get("postgres", {})
    config_dbname = pg.get("dbname", "image_scoring")
    if "POSTGRES_DB" in os.environ:
        dbname = os.environ["POSTGRES_DB"]
    else:
        dbname = config_dbname

    if _pytest_active():
        if postgres_production_allowed_in_pytest():
            pass  # keep dbname from POSTGRES_DB / config above
        else:
            if _env_truthy(POSTGRES_PRODUCTION_IN_PYTEST_ENV) and not _env_truthy(
                POSTGRES_PRODUCTION_PYTEST_RISK_ACCEPTED_ENV
            ):
                if not _warned_production_pytest_incomplete:
                    logger.warning(
                        "%s is set but pytest still uses %r unless %s is also set (dangerous).",
                        POSTGRES_PRODUCTION_IN_PYTEST_ENV,
                        POSTGRES_TEST_DB,
                        POSTGRES_PRODUCTION_PYTEST_RISK_ACCEPTED_ENV,
                    )
                    _warned_production_pytest_incomplete = True
            dbname = POSTGRES_TEST_DB
    return {
        "host": os.environ.get("POSTGRES_HOST", pg.get("host", "127.0.0.1")),
        "port": int(os.environ.get("POSTGRES_PORT", pg.get("port", 5432))),
        "dbname": dbname,
        "user": os.environ.get("POSTGRES_USER", pg.get("user", "postgres")),
        "password": os.environ.get("POSTGRES_PASSWORD", pg.get("password", "postgres")),
    }

def init_pool():
    global _pool
    if _pool is None:
        cfg = get_pg_config()
        try:
            _pool = ThreadedConnectionPool(
                1, 20,
                host=cfg["host"],
                port=cfg["port"],
                dbname=cfg["dbname"],
                user=cfg["user"],
                password=cfg["password"]
            )
            logger.info("PostgreSQL connection pool initialized.")
        except Exception as e:
            logger.error("Failed to initialize PostgreSQL connection pool: %s", e)

def get_pg_connection():
    global _pool
    if _pool is None:
        init_pool()
    if _pool:
        conn = _pool.getconn()
        try:
            register_vector(conn)
        except Exception as e:
            logger.warning("Failed to register pgvector on connection: %s", e)
        return conn
    raise Exception("PostgreSQL connection pool is not initialized")

def release_pg_connection(conn):
    global _pool
    if _pool and conn:
        _pool.putconn(conn)


def close_pool():
    """Close all pooled connections and drop the pool (e.g. after POSTGRES_DB or host changes)."""
    global _pool
    if _pool is not None:
        try:
            _pool.closeall()
        except Exception as e:
            logger.warning("Error while closing PostgreSQL pool: %s", e)
        finally:
            _pool = None


def reset_pool():
    """Alias for :func:`close_pool` (tests and fixtures)."""
    close_pool()


# Application tables for bulk TRUNCATE (CASCADE handles FK order).
def _quoted_db_identifier(name: str) -> str:
    """Quote a database name for DDL. Only allows safe unquoted-style identifiers."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(f"Refusing CREATE DATABASE for unsafe name: {name!r}")
    return '"' + name.replace('"', '""') + '"'


POSTGRES_APP_TABLES = (
    "jobs",
    "folders",
    "stacks",
    "image_embeddings",
    "embedding_spaces",
    "images",
    "file_paths",
    "job_phases",
    "job_steps",
    "job_image_actions",
    "image_incidents",
    "image_exif",
    "image_xmp",
    "cluster_progress",
    "culling_sessions",
    "culling_picks",
    "pipeline_phases",
    "image_phase_status",
    "stack_cache",
    "keywords_dim",
    "image_keywords",
    "deleted_images",
)

# Default visual-embedding catalog row (re-applied after TRUNCATE in tests).
_SEED_DEFAULT_EMBEDDING_SPACE_SQL = """
            INSERT INTO embedding_spaces (code, dim, description, active)
            SELECT 'mobilenet_v2_imagenet_gap', 1280,
                   'MobileNetV2 ImageNet weights, GAP — visual similarity / culling', 1
            WHERE NOT EXISTS (SELECT 1 FROM embedding_spaces WHERE code = 'mobilenet_v2_imagenet_gap')
            """


def ensure_database_exists(dbname: str, admin_dbname: str = "postgres") -> None:
    """
    Create database ``dbname`` if missing. Uses host/port/user/password from
    config and env (same as :func:`get_pg_config`), but connects to ``admin_dbname``
    for the CREATE DATABASE statement.
    """
    db_config = config.get_config_section("database") or {}
    pg = db_config.get("postgres", {})
    host = os.environ.get("POSTGRES_HOST", pg.get("host", "127.0.0.1"))
    port = int(os.environ.get("POSTGRES_PORT", pg.get("port", 5432)))
    user = os.environ.get("POSTGRES_USER", pg.get("user", "postgres"))
    password = os.environ.get("POSTGRES_PASSWORD", pg.get("password", "postgres"))
    conn = psycopg2.connect(
        host=host,
        port=port,
        dbname=admin_dbname,
        user=user,
        password=password,
        options="-c client_encoding=UTF8",
    )
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
            if cur.fetchone():
                return
            cur.execute(f"CREATE DATABASE {_quoted_db_identifier(dbname)}")
            logger.info("Created PostgreSQL database %s", dbname)
    finally:
        conn.close()


def truncate_app_tables() -> None:
    """TRUNCATE all application tables and restart sequences (uses current pool)."""
    cfg = get_pg_config()
    if cfg["dbname"] != POSTGRES_TEST_DB and not postgres_production_allowed_in_pytest():
        raise RuntimeError(
            f"truncate_app_tables refused: current PostgreSQL database is {cfg['dbname']!r}, "
            f"expected {POSTGRES_TEST_DB!r}. Under pytest, POSTGRES_DB and config dbname are ignored "
            f"unless both {POSTGRES_PRODUCTION_IN_PYTEST_ENV} and "
            f"{POSTGRES_PRODUCTION_PYTEST_RISK_ACCEPTED_ENV} are set."
        )
    table_list = ", ".join(POSTGRES_APP_TABLES)
    with PGConnectionManager(commit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f"TRUNCATE {table_list} RESTART IDENTITY CASCADE")
            cur.execute(_SEED_DEFAULT_EMBEDDING_SPACE_SQL)
            try:
                from modules.phases import SEED_PHASES

                for phase in SEED_PHASES:
                    code = phase["code"].value if hasattr(phase["code"], "value") else str(phase["code"])
                    cur.execute(
                        """
                        INSERT INTO pipeline_phases (code, name, description, sort_order, enabled, optional, default_skip)
                        VALUES (%s, %s, %s, %s, TRUE, %s, %s)
                        ON CONFLICT (code) DO UPDATE
                        SET optional = EXCLUDED.optional, default_skip = EXCLUDED.default_skip
                        """,
                        (
                            code,
                            phase["name"],
                            phase.get("description", ""),
                            int(phase["sort_order"]),
                            True if phase.get("optional") else False,
                            True if phase.get("default_skip") else False,
                        ),
                    )
            except Exception:
                # Best-effort: tests that do not depend on pipeline_phases should still run.
                pass


class PGConnectionManager:
    """Context manager for PostgreSQL connections from the pool."""
    def __init__(self, commit=False):
        self.commit = commit
        self.conn = None

    def __enter__(self):
        self.conn = get_pg_connection()
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            if exc_type is None and self.commit:
                self.conn.commit()
            elif exc_type is not None:
                self.conn.rollback()
            release_pg_connection(self.conn)

def execute_select(sql: str, params=None) -> list[dict]:
    """Execute a (pre-translated) SELECT on PostgreSQL and return a list of dicts."""
    with PGConnectionManager() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


def execute_select_one(sql: str, params=None) -> "dict | None":
    """Execute a SELECT and return the first row as a dict, or None."""
    rows = execute_select(sql, params)
    return rows[0] if rows else None


def execute_write(sql: str, params=None) -> int:
    """Execute INSERT/UPDATE/DELETE on PostgreSQL and return rowcount."""
    with PGConnectionManager(commit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount


def execute_write_returning(sql: str, params=None) -> "dict | None":
    """Execute INSERT/UPDATE ... RETURNING on PostgreSQL, return first row as dict."""
    with PGConnectionManager(commit=True) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None


def init_db():
    """Initialize PostgreSQL database schema (full parity with Firebird schema)."""
    import time

    from psycopg2 import DatabaseError

    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        try:
            _init_db_transaction()
            return
        except DatabaseError as e:
            # DeadlockDetected subclasses DatabaseError, not OperationalError (psycopg2 2.9+).
            pgcode = getattr(e, "pgcode", None)
            is_deadlock = pgcode == "40P01" or "deadlock" in str(e).lower()
            if is_deadlock and attempt < max_attempts:
                wait = min(2.0, 0.25 * (2 ** (attempt - 1)))
                logger.warning(
                    "PostgreSQL schema init deadlock (attempt %s/%s), retrying in %.2fs: %s",
                    attempt,
                    max_attempts,
                    wait,
                    e,
                )
                time.sleep(wait)
                continue
            raise


def _init_db_transaction():
    """Run DDL in one transaction (see :func:`init_db` for deadlock retries)."""
    with PGConnectionManager(commit=True) as conn:
        with conn.cursor() as cur:
            # Enable pgvector
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

            # ------------------------------------------------------------------
            # FOLDERS
            # ------------------------------------------------------------------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS folders (
                id                  SERIAL PRIMARY KEY,
                path                VARCHAR(4000),
                parent_id           INTEGER REFERENCES folders(id) ON DELETE CASCADE,
                is_fully_scored     SMALLINT DEFAULT 0,
                is_keywords_processed SMALLINT DEFAULT 0,
                phase_agg_dirty     INTEGER DEFAULT 1,
                phase_agg_updated_at TIMESTAMP,
                phase_agg_json      TEXT,
                image_count         INTEGER DEFAULT 0,
                created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_folders_path ON folders(path);")
            cur.execute("ALTER TABLE folders ADD COLUMN IF NOT EXISTS image_count INTEGER DEFAULT 0;")

            # ------------------------------------------------------------------
            # STACKS
            # ------------------------------------------------------------------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS stacks (
                id              SERIAL PRIMARY KEY,
                name            VARCHAR(255),
                best_image_id   INTEGER,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # ------------------------------------------------------------------
            # JOBS  (full column set matching Firebird schema)
            # ------------------------------------------------------------------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id                  SERIAL PRIMARY KEY,
                input_path          VARCHAR(4000),
                phase_id            INTEGER,
                job_type            VARCHAR(50),
                status              VARCHAR(50),
                priority            SMALLINT DEFAULT 100,
                retry_count         INTEGER DEFAULT 0,
                target_scope        VARCHAR(255),
                paused_at           TIMESTAMP,
                queue_position      INTEGER,
                cancel_requested    SMALLINT DEFAULT 0,
                queue_payload       TEXT,
                scope_type          VARCHAR(30),
                scope_paths         TEXT,
                created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                enqueued_at         TIMESTAMP,
                started_at          TIMESTAMP,
                finished_at         TIMESTAMP,
                completed_at        TIMESTAMP,
                log                 TEXT,
                current_phase       VARCHAR(50),
                next_phase_index    INTEGER,
                runner_state        VARCHAR(50),
                description         TEXT,
                report_json         JSONB
            );
            """)

            # ------------------------------------------------------------------
            # JOB_PHASES — persisted multi-step pipeline plans
            # ------------------------------------------------------------------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS job_phases (
                id              SERIAL PRIMARY KEY,
                job_id          INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                phase_order     INTEGER NOT NULL,
                phase_code      VARCHAR(50) NOT NULL,
                state           VARCHAR(20) NOT NULL,
                started_at      TIMESTAMP,
                completed_at    TIMESTAMP,
                error_message   TEXT
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_job_phases_job_id ON job_phases(job_id);")
            cur.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS description TEXT;")
            cur.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS report_json JSONB;")

            # job_phases counter columns
            cur.execute("ALTER TABLE job_phases ADD COLUMN IF NOT EXISTS images_in_scope INTEGER DEFAULT 0;")
            cur.execute("ALTER TABLE job_phases ADD COLUMN IF NOT EXISTS images_targeted INTEGER DEFAULT 0;")
            cur.execute("ALTER TABLE job_phases ADD COLUMN IF NOT EXISTS images_processed INTEGER DEFAULT 0;")
            cur.execute("ALTER TABLE job_phases ADD COLUMN IF NOT EXISTS images_skipped INTEGER DEFAULT 0;")
            cur.execute("ALTER TABLE job_phases ADD COLUMN IF NOT EXISTS images_failed INTEGER DEFAULT 0;")

            # ------------------------------------------------------------------
            # JOB_STEPS — sub-phase telemetry
            # ------------------------------------------------------------------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS job_steps (
                id              SERIAL PRIMARY KEY,
                job_id          INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                phase_code      VARCHAR(50) NOT NULL,
                step_code       VARCHAR(50) NOT NULL,
                step_name       VARCHAR(100) NOT NULL,
                status          VARCHAR(20) DEFAULT 'pending',
                started_at      TIMESTAMP,
                completed_at    TIMESTAMP,
                items_total     INTEGER DEFAULT 0,
                items_done      INTEGER DEFAULT 0,
                throughput_rps  DOUBLE PRECISION,
                error_message   TEXT
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_job_steps_job_id ON job_steps(job_id);")

            # ------------------------------------------------------------------
            # JOB_IMAGE_ACTIONS — per-image execution trail with before/after snapshots
            # ------------------------------------------------------------------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS job_image_actions (
                id              SERIAL PRIMARY KEY,
                job_id          INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                image_id        INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
                phase_code      VARCHAR(50) NOT NULL,
                action          VARCHAR(30) NOT NULL,
                reason          TEXT,
                before_snapshot JSONB,
                after_snapshot  JSONB,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_jia_job_id ON job_image_actions(job_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_jia_job_phase ON job_image_actions(job_id, phase_code);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_jia_image_id ON job_image_actions(image_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_jia_created_at ON job_image_actions(created_at);")

            # ------------------------------------------------------------------
            # IMAGES  (full column set)
            # ------------------------------------------------------------------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS images (
                id                  SERIAL PRIMARY KEY,
                job_id              INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
                file_path           VARCHAR(4000),
                file_name           VARCHAR(255),
                file_type           VARCHAR(20),
                score               DOUBLE PRECISION,
                score_general       DOUBLE PRECISION,
                score_technical     DOUBLE PRECISION,
                score_aesthetic     DOUBLE PRECISION,
                score_spaq          DOUBLE PRECISION,
                score_ava           DOUBLE PRECISION,
                score_koniq         DOUBLE PRECISION,
                score_paq2piq       DOUBLE PRECISION,
                score_liqe          DOUBLE PRECISION,
                keywords            TEXT,
                title               VARCHAR(500),
                description         TEXT,
                metadata            TEXT,
                thumbnail_path      VARCHAR(4000),
                thumbnail_path_win  VARCHAR(4000),
                scores_json         TEXT,
                model_version       VARCHAR(50),
                rating              SMALLINT,
                label               VARCHAR(50),
                image_hash          VARCHAR(64),
                hash_version        INTEGER NOT NULL DEFAULT 1,
                folder_id           INTEGER REFERENCES folders(id) ON DELETE SET NULL,
                stack_id            INTEGER REFERENCES stacks(id) ON DELETE SET NULL,
                burst_uuid          VARCHAR(64),
                cull_decision       VARCHAR(20),
                cull_policy_version VARCHAR(50),
                image_uuid          VARCHAR(36),
                created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at          TIMESTAMP,
                image_embedding     vector(1280)
            );
            """)
            cur.execute(
                "ALTER TABLE images ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;"
            )
            cur.execute(
                "ALTER TABLE images ADD COLUMN IF NOT EXISTS hash_version INTEGER NOT NULL DEFAULT 1;"
            )
            cur.execute(
                "UPDATE images SET updated_at = COALESCE(created_at, CURRENT_TIMESTAMP) "
                "WHERE updated_at IS NULL"
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_images_folder_id ON images(folder_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_images_stack_id ON images(stack_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_images_hash ON images(image_hash);")
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_images_image_hash_hash_version "
                "ON images(image_hash, hash_version) WHERE image_hash IS NOT NULL;"
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_images_burst_uuid ON images(burst_uuid);")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_images_image_uuid ON images(image_uuid) WHERE image_uuid IS NOT NULL;")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_images_file_path ON images(file_path);")
            # HNSW cosine index for fast similarity search
            cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_images_embedding_hnsw
              ON images USING hnsw (image_embedding vector_cosine_ops);
            """)

            # ------------------------------------------------------------------
            # EMBEDDING_SPACES — registry of vector kinds (fixed dim per row)
            # ------------------------------------------------------------------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS embedding_spaces (
                id              SERIAL PRIMARY KEY,
                code            VARCHAR(64) NOT NULL,
                dim             INTEGER NOT NULL,
                description     TEXT,
                active          SMALLINT DEFAULT 1 NOT NULL,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_embedding_spaces_code ON embedding_spaces(code);")

            # ------------------------------------------------------------------
            # IMAGE_EMBEDDINGS — one row per (image, space); vector(1280) for 1280-d spaces only
            # ------------------------------------------------------------------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS image_embeddings (
                id                      SERIAL PRIMARY KEY,
                image_id                INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
                embedding_space_id      INTEGER NOT NULL REFERENCES embedding_spaces(id) ON DELETE CASCADE,
                embedding               vector(1280) NOT NULL,
                model_version           VARCHAR(64),
                updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (image_id, embedding_space_id)
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_image_embeddings_image ON image_embeddings(image_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_image_embeddings_space ON image_embeddings(embedding_space_id);")
            cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_image_embeddings_hnsw
              ON image_embeddings USING hnsw (embedding vector_cosine_ops);
            """)

            cur.execute(_SEED_DEFAULT_EMBEDDING_SPACE_SQL)

            # Back-fill FK on stacks.best_image_id now that images exists
            # (Firebird adds this as a separate alter; we declare it inline above for stacks
            #  but stacks was created before images — add it as a constraint now)
            cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE constraint_name = 'fk_stacks_best_image'
                ) THEN
                    ALTER TABLE stacks
                      ADD CONSTRAINT fk_stacks_best_image
                      FOREIGN KEY (best_image_id) REFERENCES images(id) ON DELETE SET NULL;
                END IF;
            END$$;
            """)

            # ------------------------------------------------------------------
            # FILE_PATHS
            # ------------------------------------------------------------------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS file_paths (
                id                  SERIAL PRIMARY KEY,
                image_id            INTEGER REFERENCES images(id) ON DELETE CASCADE,
                path                VARCHAR(4000),
                last_seen           TIMESTAMP,
                path_type           VARCHAR(10),
                is_verified         SMALLINT DEFAULT 0,
                verification_date   TIMESTAMP
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_file_paths_img_type ON file_paths(image_id, path_type);")
            cur.execute(
                "SELECT 1 FROM pg_indexes WHERE schemaname = ANY (current_schemas(false)) "
                "AND indexname = 'uq_file_paths_image_id_path'"
            )
            if cur.fetchone() is None:
                cur.execute(
                    """
                    DELETE FROM file_paths AS fp1
                    USING file_paths AS fp2
                    WHERE fp1.id > fp2.id
                      AND fp1.image_id IS NOT DISTINCT FROM fp2.image_id
                      AND fp1.path IS NOT DISTINCT FROM fp2.path
                    """
                )
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_file_paths_image_id_path "
                "ON file_paths(image_id, path);"
            )

            # ------------------------------------------------------------------
            # CLUSTER_PROGRESS
            # ------------------------------------------------------------------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS cluster_progress (
                folder_path VARCHAR(512) NOT NULL PRIMARY KEY,
                last_run    TIMESTAMP
            );
            """)

            # ------------------------------------------------------------------
            # CULLING_SESSIONS
            # ------------------------------------------------------------------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS culling_sessions (
                id                  SERIAL PRIMARY KEY,
                folder_path         VARCHAR(4000),
                mode                VARCHAR(50),
                status              VARCHAR(50) DEFAULT 'active',
                total_images        INTEGER DEFAULT 0,
                total_groups        INTEGER DEFAULT 0,
                reviewed_groups     INTEGER DEFAULT 0,
                picked_count        INTEGER DEFAULT 0,
                rejected_count      INTEGER DEFAULT 0,
                created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at        TIMESTAMP
            );
            """)

            # ------------------------------------------------------------------
            # CULLING_PICKS
            # ------------------------------------------------------------------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS culling_picks (
                id                  SERIAL PRIMARY KEY,
                session_id          INTEGER REFERENCES culling_sessions(id) ON DELETE CASCADE,
                image_id            INTEGER REFERENCES images(id) ON DELETE CASCADE,
                group_id            INTEGER,
                decision            VARCHAR(50),
                auto_suggested      SMALLINT DEFAULT 0,
                is_best_in_group    SMALLINT DEFAULT 0,
                created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_culling_picks_session ON culling_picks(session_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_culling_picks_image ON culling_picks(image_id);")

            # ------------------------------------------------------------------
            # IMAGE_EXIF — cached EXIF metadata (one row per image)
            # ------------------------------------------------------------------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS image_exif (
                image_id                INTEGER NOT NULL PRIMARY KEY REFERENCES images(id) ON DELETE CASCADE,
                make                    VARCHAR(100),
                model                   VARCHAR(200),
                lens_model              VARCHAR(255),
                focal_length            VARCHAR(50),
                focal_length_35mm       SMALLINT,
                date_time_original      TIMESTAMP,
                create_date             TIMESTAMP,
                exposure_time           VARCHAR(30),
                f_number                VARCHAR(20),
                iso                     INTEGER,
                exposure_compensation   VARCHAR(20),
                image_width             INTEGER,
                image_height            INTEGER,
                orientation             SMALLINT,
                flash                   SMALLINT,
                image_unique_id         VARCHAR(64),
                shutter_count           INTEGER,
                sub_sec_time_original   VARCHAR(10),
                extracted_at            TIMESTAMP
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_image_exif_date ON image_exif(date_time_original);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_image_exif_make ON image_exif(make);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_image_exif_model ON image_exif(model);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_image_exif_lens ON image_exif(lens_model);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_image_exif_iso ON image_exif(iso);")

            # ------------------------------------------------------------------
            # IMAGE_XMP — cached XMP sidecar metadata (one row per image)
            # ------------------------------------------------------------------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS image_xmp (
                image_id        INTEGER NOT NULL PRIMARY KEY REFERENCES images(id) ON DELETE CASCADE,
                rating          SMALLINT,
                label           VARCHAR(50),
                pick_status     SMALLINT,
                burst_uuid      VARCHAR(64),
                stack_id        VARCHAR(64),
                keywords        TEXT,
                title           VARCHAR(500),
                description     TEXT,
                create_date     TIMESTAMP,
                modify_date     TIMESTAMP,
                extracted_at    TIMESTAMP
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_image_xmp_burst ON image_xmp(burst_uuid);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_image_xmp_pick ON image_xmp(pick_status);")

            # ------------------------------------------------------------------
            # PIPELINE_PHASES — phase registry
            # ------------------------------------------------------------------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_phases (
                id              SERIAL PRIMARY KEY,
                code            VARCHAR(50) NOT NULL,
                name            VARCHAR(100) NOT NULL,
                description     TEXT,
                sort_order      INTEGER DEFAULT 0 NOT NULL,
                enabled         SMALLINT DEFAULT 1 NOT NULL,
                optional        SMALLINT DEFAULT 0 NOT NULL,
                default_skip    SMALLINT DEFAULT 0 NOT NULL
            );
            """)
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_pipeline_phases_code ON pipeline_phases(code);")

            # ------------------------------------------------------------------
            # IMAGE_PHASE_STATUS — per-image per-phase tracking
            # ------------------------------------------------------------------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS image_phase_status (
                id                  SERIAL PRIMARY KEY,
                image_id            INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
                phase_id            INTEGER NOT NULL REFERENCES pipeline_phases(id),
                status              VARCHAR(20) DEFAULT 'not_started' NOT NULL,
                executor_version    VARCHAR(50),
                app_version         VARCHAR(50),
                job_id              INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
                attempt_count       SMALLINT DEFAULT 0 NOT NULL,
                last_error          TEXT,
                started_at          TIMESTAMP,
                finished_at         TIMESTAMP,
                updated_at          TIMESTAMP,
                skip_reason         TEXT,
                skipped_by          VARCHAR(255)
            );
            """)
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_image_phase ON image_phase_status(image_id, phase_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ips_image_id ON image_phase_status(image_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ips_phase_id ON image_phase_status(phase_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ips_status ON image_phase_status(status);")

            # ------------------------------------------------------------------
            # IMAGE_INCIDENTS — append-only image-scoped failures / validations
            # ------------------------------------------------------------------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS image_incidents (
                id              SERIAL PRIMARY KEY,
                image_id        INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
                folder_id       INTEGER REFERENCES folders(id) ON DELETE SET NULL,
                job_id          INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
                phase_id        INTEGER REFERENCES pipeline_phases(id) ON DELETE SET NULL,
                kind            VARCHAR(32) NOT NULL,
                source          VARCHAR(128),
                message         TEXT NOT NULL,
                detail          JSONB,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_image_incidents_created_at "
                "ON image_incidents (created_at DESC);"
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_image_incidents_image_id ON image_incidents(image_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_image_incidents_folder_id ON image_incidents(folder_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_image_incidents_job_id ON image_incidents(job_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_image_incidents_kind ON image_incidents(kind);")

            # ------------------------------------------------------------------
            # STACK_CACHE — pre-computed score aggregates per stack
            # (created by Electron but defined here for Postgres parity)
            # ------------------------------------------------------------------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS stack_cache (
                stack_id                INTEGER NOT NULL PRIMARY KEY REFERENCES stacks(id) ON DELETE CASCADE,
                image_count             INTEGER DEFAULT 0,
                rep_image_id            INTEGER REFERENCES images(id) ON DELETE SET NULL,
                min_score_general       DOUBLE PRECISION,
                max_score_general       DOUBLE PRECISION,
                min_score_technical     DOUBLE PRECISION,
                max_score_technical     DOUBLE PRECISION,
                min_score_aesthetic     DOUBLE PRECISION,
                max_score_aesthetic     DOUBLE PRECISION,
                min_score_spaq          DOUBLE PRECISION,
                max_score_spaq          DOUBLE PRECISION,
                min_score_ava           DOUBLE PRECISION,
                max_score_ava           DOUBLE PRECISION,
                min_score_liqe          DOUBLE PRECISION,
                max_score_liqe          DOUBLE PRECISION,
                min_rating              INTEGER,
                max_rating              INTEGER,
                min_created_at          TIMESTAMP,
                max_created_at          TIMESTAMP,
                folder_id               INTEGER REFERENCES folders(id) ON DELETE SET NULL
            );
            """)

            # ------------------------------------------------------------------
            # KEYWORDS_DIM — normalized keyword dictionary
            # ------------------------------------------------------------------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS keywords_dim (
                keyword_id      SERIAL PRIMARY KEY,
                keyword_norm    VARCHAR(200) NOT NULL,
                keyword_display VARCHAR(200),
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_keywords_dim_norm ON keywords_dim(keyword_norm);")

            # ------------------------------------------------------------------
            # IMAGE_KEYWORDS — many-to-many junction (image <-> keyword)
            # ------------------------------------------------------------------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS image_keywords (
                image_id    INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
                keyword_id  INTEGER NOT NULL REFERENCES keywords_dim(keyword_id) ON DELETE CASCADE,
                source      VARCHAR(128) DEFAULT 'auto',
                confidence  DOUBLE PRECISION,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (image_id, keyword_id)
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_imgkw_image_id ON image_keywords(image_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_imgkw_keyword_id ON image_keywords(keyword_id);")
            try:
                cur.execute(
                    "ALTER TABLE image_keywords ALTER COLUMN source TYPE VARCHAR(128)"
                )
            except Exception as e:
                logger.debug("image_keywords.source widen (optional): %s", e)

            # ------------------------------------------------------------------
            # DELETED_IMAGES — tombstone rows when an images row is removed (Sync/Import/Backup)
            # ------------------------------------------------------------------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS deleted_images (
                id              SERIAL PRIMARY KEY,
                original_id     INTEGER,
                image_uuid      VARCHAR(36),
                image_hash      VARCHAR(64),
                file_name       VARCHAR(255),
                original_path   VARCHAR(4000),
                deleted_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_deleted_images_original_id ON deleted_images(original_id);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_deleted_images_uuid ON deleted_images(image_uuid) "
                "WHERE image_uuid IS NOT NULL;"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_deleted_images_hash ON deleted_images(image_hash) "
                "WHERE image_hash IS NOT NULL;"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_deleted_images_file_uuid ON deleted_images(file_name, image_uuid) "
                "WHERE image_uuid IS NOT NULL;"
            )
            cur.execute("""
            CREATE OR REPLACE FUNCTION trg_record_deleted_image_fn()
            RETURNS TRIGGER AS $$
            BEGIN
                INSERT INTO deleted_images (original_id, image_uuid, image_hash, file_name, original_path)
                VALUES (OLD.id, OLD.image_uuid, OLD.image_hash, OLD.file_name, OLD.file_path);
                RETURN OLD;
            END;
            $$ LANGUAGE plpgsql;
            """)
            cur.execute("DROP TRIGGER IF EXISTS trg_record_deleted_image ON images;")
            cur.execute("""
            CREATE TRIGGER trg_record_deleted_image
                BEFORE DELETE ON images
                FOR EACH ROW
                EXECUTE PROCEDURE trg_record_deleted_image_fn();
            """)

            logger.info("PostgreSQL schema initialization completed.")
