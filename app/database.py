import os
import psycopg2
import psycopg2.extensions
from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# PostgreSQL connection config built from .env
# ---------------------------------------------------------------------------
PG_CONFIG = dict(
    host=os.getenv("PG_HOST", "localhost"),
    port=int(os.getenv("PG_PORT", "5432")),
    dbname=os.getenv("PG_DB", "ragdb"),
    user=os.getenv("PG_USER", "postgres"),
    password=os.getenv("PG_PASSWORD", ""),
)


def get_connection():
    """
    Returns a new psycopg2 connection.
    Always call conn.close() after use, or use it inside a with/try-finally block.
    """
    return psycopg2.connect(**PG_CONFIG)


def rollback_if_aborted(conn):
    """
    Roll back a stuck/aborted transaction so the connection is usable again.
    """
    if conn.status == psycopg2.extensions.STATUS_IN_TRANSACTION:
        try:
            conn.rollback()
        except Exception:
            pass