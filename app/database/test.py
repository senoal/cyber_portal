"""Minimal local SQLite health check; never contacts a database server."""
import sqlite3

from app.config import Config

def test_connection():
    try:
        with sqlite3.connect(Config.SQLITE_PATH) as conn:
            version = conn.execute("SELECT sqlite_version()").fetchone()[0]
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        print(f"SQLite {version}; integrity={integrity}")
    except sqlite3.Error as error:
        print(f"SQLite tidak tersedia: {error}")

if __name__ == "__main__":
    test_connection()
