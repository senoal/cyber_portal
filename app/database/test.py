"""Health check for the database backend selected by SEC_APP configuration."""

from app.database.db import get_connection, is_sqlite

def test_connection():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        if is_sqlite():
            cursor.execute("SELECT sqlite_version()")
            version = cursor.fetchone()[0]
            cursor.execute("PRAGMA integrity_check")
            print(f"SQLite {version}; integrity={cursor.fetchone()[0]}")
        else:
            cursor.execute("SELECT DB_NAME(), CAST(SERVERPROPERTY('ProductVersion') AS varchar(128))")
            database, version = cursor.fetchone()
            print(f"MSSQL database={database}; version={version}")
        conn.close()
    except Exception as error:
        print(f"Database tidak tersedia: {error}")

if __name__ == "__main__":
    test_connection()
