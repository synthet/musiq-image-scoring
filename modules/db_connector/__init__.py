"""
db_connector — transport-layer abstraction for database access.

Provides a unified IConnector interface that hides PostgreSQL /
HTTP-proxy differences from callers.  SQL may use legacy ``?``
placeholders; the PostgresConnector translates them to ``%s`` via
``_translate_fb_to_pg`` internally.

Usage::

    from modules.db_connector import get_connector

    # Simple read
    rows = get_connector().query("SELECT * FROM images WHERE id = ?", (image_id,))

    # Write
    get_connector().execute("UPDATE images SET rating = ? WHERE id = ?", (5, image_id))

    # Transaction
    def _tx(tx):
        rows = tx.execute_returning(
            "INSERT INTO jobs (input_path, status) VALUES (?, ?) RETURNING id",
            (path, "queued"),
        )
        job_id = rows[0]["id"]
        tx.execute("UPDATE jobs SET queue_position = ? WHERE id = ?", (job_id, job_id))
        return job_id

    job_id = get_connector().run_transaction(_tx)

Implementations
---------------
PostgresConnector  — psycopg2 pool    (``database.engine = "postgres"``)
ApiConnector       — HTTP proxy        (``database.engine = "api"``)

Note: FirebirdConnector was removed in 2026-03 (Firebird decommissioned).
Legacy ``engine = "firebird"`` config values are mapped to PostgresConnector.

Factory configuration
---------------------
Set ``database.engine`` in config.json (see :func:`modules.config.get_database_engine`).
The singleton is created lazily on the first call to ``get_connector()``.
Use ``reset_connector()`` in tests.
"""
from modules.db_connector.factory import get_connector, reset_connector
from modules.db_connector.protocol import IConnector, ITransaction

__all__ = ["IConnector", "ITransaction", "get_connector", "reset_connector"]
