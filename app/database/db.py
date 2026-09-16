"""Database factory for SQLite rollback snapshots and Microsoft SQL Server."""
import re
import sqlite3
import threading
from pathlib import Path
from app.config import Config


def _mssql_enabled():
    return Config.DATABASE_ENGINE == "mssql"


_sqlite_setup_lock = threading.Lock()
_sqlite_wal_ready = set()
# SQLite allows one writer at a time.  A page submission may overlap with an
# audit-log write or another user's save, so two seconds is unnecessarily
# short and produces avoidable "database is locked" failures.
_SQLITE_BUSY_TIMEOUT_MS = 10_000

def is_sqlite():
    return not _mssql_enabled()

class _AttrRow(tuple):
    """Row supporting the tuple and attribute access used by the models."""
    def __new__(cls, values, names):
        obj = super().__new__(cls, values); obj._names = names; return obj
    def __getattr__(self, name):
        try: return self[self._names.index(name)]
        except ValueError: raise AttributeError(name) from None

def _row_factory(cursor, row):
    return _AttrRow(row, [item[0] for item in cursor.description])

def _date_part(value, part):
    """SQLite functions matching the small SQL Server YEAR/MONTH usage here."""
    if value is None:
        return None
    text = str(value)
    try:
        return int(text[5:7] if part == "month" else text[:4])
    except (TypeError, ValueError):
        return None

def _date_from_parts(year, month, day):
    try:
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    except (TypeError, ValueError):
        return None

class _SqliteCursor:
    """Compatibility layer for existing parameterised MSSQL queries."""
    def __init__(self, cursor): self._cursor, self._generated_id = cursor, None
    def execute(self, sql, params=()):
        # sqlite3 requires a sequence for one placeholder; older model calls
        # use the convenient scalar form.
        if params is not None and not isinstance(params, (tuple, list)):
            params = (params,)
        sql = re.sub(r"\bdbo\.", "", sql, flags=re.I)
        sql = re.sub(r"CAST\s*\(\s*GETDATE\s*\(\)\s+AS\s+DATE\s*\)", "date('now')", sql, flags=re.I)
        sql = re.sub(r"\bISNULL\s*\(", "COALESCE(", sql, flags=re.I)
        sql = re.sub(r"\bGETDATE\s*\(\)", "CURRENT_TIMESTAMP", sql, flags=re.I)
        sql = re.sub(r"\bSYS(?:UTC)?DATETIME\s*\(\)", "CURRENT_TIMESTAMP", sql, flags=re.I)
        paged = re.search(r"\s+OFFSET\s+\?\s+ROWS\s+FETCH\s+NEXT\s+\?\s+ROWS\s+ONLY", sql, re.I)
        if paged and len(params) >= 2:
            # MSSQL binds OFFSET, FETCH; SQLite binds LIMIT, OFFSET.
            params = [*params[:-2], params[-1], params[-2]]
        sql = re.sub(r"\s+OFFSET\s+\?\s+ROWS\s+FETCH\s+NEXT\s+\?\s+ROWS\s+ONLY", " LIMIT ? OFFSET ?", sql, flags=re.I)
        sql = re.sub(r"\s+OFFSET\s+(\d+)\s+ROWS\s+FETCH\s+NEXT\s+(\d+)\s+ROWS\s+ONLY", r" LIMIT \2 OFFSET \1", sql, flags=re.I)
        top = re.search(r"SELECT\s+TOP\s+(\d+)", sql, re.I)
        if top:
            sql = sql[:top.start()] + "SELECT" + sql[top.end():].rstrip().rstrip(";") + " LIMIT " + top.group(1)
        match = re.search(r"\s+OUTPUT\s+INSERTED\.([A-Za-z_][\w]*)", sql, re.I)
        self._generated_id = None
        if match: sql = sql[:match.start()] + sql[match.end():]
        self._cursor.execute(sql, params)
        if match: self._generated_id = self._cursor.lastrowid
        return self
    def executemany(self, sql, params):
        for item in params: self.execute(sql, item)
        return self
    def fetchone(self): return (self._generated_id,) if self._generated_id is not None else self._cursor.fetchone()
    def fetchall(self): return self._cursor.fetchall()
    @property
    def description(self): return self._cursor.description
    @property
    def rowcount(self): return self._cursor.rowcount
    def __getattr__(self, name): return getattr(self._cursor, name)

class _SqliteConnection:
    def __init__(self, conn): self._conn = conn
    def cursor(self): return _SqliteCursor(self._conn.cursor())
    def __getattr__(self, name): return getattr(self._conn, name)


class _MssqlCursor:
    """Provide the tuple-and-attribute row interface expected by the models."""
    def __init__(self, cursor):
        self._cursor = cursor
        self._names = []

    def execute(self, sql, params=()):
        if params is not None and not isinstance(params, (tuple, list)):
            params = (params,)
        # Existing models use the ODBC ``?`` parameter marker; pymssql uses
        # ``%s``. SQL syntax otherwise remains native SQL Server.
        self._cursor.execute(sql.replace("?", "%s"), tuple(params or ()))
        self._names = [item[0] for item in (self._cursor.description or [])]
        return self

    def executemany(self, sql, params):
        self._cursor.executemany(sql.replace("?", "%s"), params)
        self._names = [item[0] for item in (self._cursor.description or [])]
        return self

    def _adapt(self, row):
        return None if row is None else _AttrRow(row, self._names)

    def fetchone(self): return self._adapt(self._cursor.fetchone())
    def fetchall(self): return [self._adapt(row) for row in self._cursor.fetchall()]
    @property
    def description(self): return self._cursor.description
    @property
    def rowcount(self): return self._cursor.rowcount
    def __getattr__(self, name): return getattr(self._cursor, name)


class _MssqlConnection:
    def __init__(self, conn): self._conn = conn
    def cursor(self): return _MssqlCursor(self._conn.cursor())
    def __getattr__(self, name): return getattr(self._conn, name)


def _get_mssql_connection():
    if not all((Config.MSSQL_SERVER, Config.MSSQL_DATABASE, Config.MSSQL_UID, Config.MSSQL_PASSWORD)):
        raise RuntimeError("Konfigurasi MSSQL belum lengkap. Atur SEC_APP_DB_SERVER, _DATABASE, _UID, dan _PASSWORD.")
    try:
        import pymssql
    except ImportError as error:
        raise RuntimeError("Dependensi pymssql belum terpasang untuk koneksi MSSQL.") from error
    return _MssqlConnection(pymssql.connect(
        server=Config.MSSQL_SERVER,
        port=Config.MSSQL_PORT,
        user=Config.MSSQL_UID,
        password=Config.MSSQL_PASSWORD,
        database=Config.MSSQL_DATABASE,
        login_timeout=15,
        timeout=30,
        charset="UTF-8",
    ))

def get_connection():
    if _mssql_enabled():
        return _get_mssql_connection()
    path = Path(Config.SQLITE_PATH).resolve(); path.parent.mkdir(parents=True, exist_ok=True)
    # A web application can have a page request, audit write, and task save
    # arrive almost together. SQLite permits one writer; wait for the active
    # short transaction rather than failing the save immediately with
    # "database is locked".
    conn = sqlite3.connect(str(path), timeout=_SQLITE_BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = _row_factory
    conn.execute(f"PRAGMA busy_timeout = {_SQLITE_BUSY_TIMEOUT_MS}")
    conn.create_function("YEAR", 1, lambda value: _date_part(value, "year"))
    conn.create_function("MONTH", 1, lambda value: _date_part(value, "month"))
    conn.create_function("DATEFROMPARTS", 3, _date_from_parts)
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL is a file-level setting. Setting it on every request requires a
    # database lock itself, so initialize it only once per application process.
    with _sqlite_setup_lock:
        if path not in _sqlite_wal_ready:
            try:
                conn.execute("PRAGMA journal_mode = WAL")
            except sqlite3.OperationalError as error:
                # Another application process can be completing a short write
                # during startup.  Do not fail the request merely because WAL
                # is already being negotiated by that process.
                if "locked" not in str(error).lower() and "busy" not in str(error).lower():
                    raise
            _sqlite_wal_ready.add(path)
    return _SqliteConnection(conn)
