"""
db.py — Database adapter.
Tries Supabase (PostgreSQL) first. Falls back to SQLite if SUPABASE_DB_URL is missing or connection fails.
"""
import os, sqlite3
from dotenv import load_dotenv

load_dotenv()

SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")   # e.g. postgresql://postgres:pwd@xxx.supabase.co:5432/postgres
DUMMY_DB_PATH   = os.getenv("DUMMY_DB_PATH", "admin_dummy.db")

# Placeholder — ? for SQLite, %s for PostgreSQL
PH = "?" if not SUPABASE_DB_URL else "%s"


def _use_postgres() -> bool:
    return bool(SUPABASE_DB_URL)


def get_conn():
    if _use_postgres():
        import psycopg2, psycopg2.extras
        conn = psycopg2.connect(SUPABASE_DB_URL)
        conn.cursor_factory = psycopg2.extras.RealDictCursor
        return conn
    else:
        conn = sqlite3.connect(DUMMY_DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


def connection_label() -> str:
    return f"Supabase (PostgreSQL)" if _use_postgres() else f"SQLite fallback ({DUMMY_DB_PATH})"


def query(sql: str, params: tuple = ()) -> list[dict]:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def execute(sql: str, params: tuple = ()) -> tuple[int, int]:
    """Run a single write statement. Returns (lastrowid, rowcount)."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        return (cur.lastrowid or 0), (cur.rowcount or 0)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_transaction(statements: list[tuple]) -> list[int]:
    """Run multiple (sql, params) pairs atomically. Returns list of lastrowids."""
    conn = get_conn()
    ids = []
    try:
        cur = conn.cursor()
        for sql, params in statements:
            cur.execute(sql, params)
            ids.append(cur.lastrowid or 0)
        conn.commit()
        return ids
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_tables() -> list[str]:
    if _use_postgres():
        rows = query("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
        return [r["table_name"] for r in rows]
    else:
        rows = query("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        return [r["name"] for r in rows]
