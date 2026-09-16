"""Synchronise the SEC_APP SQLite snapshot into an existing SQL Server schema.

The source SQLite database is authoritative.  The script is deliberately
additive: it inserts missing rows and updates rows with the same logical key,
but never deletes SQL Server rows.  Run once without --apply to inspect the
delta, then run again with --apply after reviewing the output.
"""
import argparse
import os
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path

import pymssql


NATURAL_KEYS = {"app_settings": ("setting_key",)}
LOCAL_COMPATIBILITY_COLUMNS = {"pentest_tasks": {"manual_owner_name": "NVARCHAR(MAX) NULL"}}


def q(identifier):
    return "[" + identifier.replace("]", "]]" ) + "]"


def target_connection():
    values = {name: os.getenv("SEC_APP_DB_" + name, "") for name in ("SERVER", "DATABASE", "UID", "PASSWORD")}
    if not all(values.values()):
        raise SystemExit("Atur SEC_APP_DB_SERVER, _DATABASE, _UID, dan _PASSWORD.")
    return pymssql.connect(
        server=values["SERVER"], port=int(os.getenv("SEC_APP_DB_PORT", "1433")),
        user=values["UID"], password=values["PASSWORD"], database=values["DATABASE"],
        login_timeout=15, timeout=60, charset="UTF-8",
    )


def sqlite_tables(connection):
    return [row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )]


def source_columns(connection, table):
    return connection.execute("PRAGMA table_info(" + q(table) + ")").fetchall()


def dependency_order(connection, tables):
    remaining = set(tables)
    ordered = []
    while remaining:
        ready = sorted(table for table in remaining if all(
            row[2] not in remaining for row in connection.execute("PRAGMA foreign_key_list(" + q(table) + ")")
        ))
        # A cyclic relationship is not present in SEC_APP. Preserve a stable
        # order if one is introduced later; SQL Server will then report it.
        ready = ready or [sorted(remaining)[0]]
        ordered.extend(ready)
        remaining.difference_update(ready)
    return ordered


def target_columns(cursor, table):
    cursor.execute("""
        SELECT c.name
        FROM sys.columns c
        JOIN sys.tables t ON t.object_id = c.object_id
        JOIN sys.schemas s ON s.schema_id = t.schema_id
        WHERE s.name='dbo' AND t.name=%s ORDER BY c.column_id
    """, (table,))
    return [row[0] for row in cursor.fetchall()]


def target_temporal_columns(cursor, table):
    cursor.execute("""
        SELECT c.name, ty.name
        FROM sys.columns c
        JOIN sys.tables t ON t.object_id = c.object_id
        JOIN sys.schemas s ON s.schema_id = t.schema_id
        JOIN sys.types ty ON ty.user_type_id = c.user_type_id
        WHERE s.name='dbo' AND t.name=%s
          AND ty.name IN ('date','datetime','datetime2','datetimeoffset','smalldatetime','time')
    """, (table,))
    return dict(cursor.fetchall())


def coerce_temporal(value, data_type):
    """Bind SQLite timestamp text as native values, avoiding server locale parsing."""
    if value is None or not isinstance(value, str):
        return value
    text = value.strip().replace("Z", "+00:00")
    if data_type == "date":
        return date.fromisoformat(text[:10])
    if data_type == "time":
        return datetime.fromisoformat("2000-01-01T" + text).time()
    return datetime.fromisoformat(text)


def has_identity(cursor, table):
    cursor.execute("""
        SELECT 1 FROM sys.identity_columns c
        JOIN sys.tables t ON t.object_id = c.object_id
        JOIN sys.schemas s ON s.schema_id = t.schema_id
        WHERE s.name='dbo' AND t.name=%s
    """, (table,))
    return cursor.fetchone() is not None


def normalise(value):
    if isinstance(value, datetime):
        return value.replace(microsecond=0).isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, memoryview):
        return value.tobytes()
    if isinstance(value, float):
        return round(value, 10)
    # SQLite snapshots retain DATETIME2 fractional seconds as text, while the
    # current SQL Server schema uses DATETIME for several legacy tables.
    # Compare at the precision representable by both stores so an idempotent
    # run does not rewrite otherwise identical rows.
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?", value):
        return value.replace("T", " ")[:19]
    return value


def ensure_compatibility_columns(cursor, source):
    for table, columns in LOCAL_COMPATIBILITY_COLUMNS.items():
        if table not in sqlite_tables(source):
            continue
        existing = set(target_columns(cursor, table))
        for name, definition in columns.items():
            if name not in existing:
                cursor.execute("ALTER TABLE dbo." + q(table) + " ADD " + q(name) + " " + definition)
                print("SCHEMA added", table + "." + name)


def sync_table(source, cursor, table, apply):
    details = source_columns(source, table)
    source_names = [row[1] for row in details]
    pk = tuple(row[1] for row in details if row[5]) or NATURAL_KEYS.get(table, ())
    destination_names = target_columns(cursor, table)
    missing = set(source_names) - set(destination_names)
    if missing:
        raise RuntimeError(f"Target dbo.{table} lacks source columns: {sorted(missing)}")
    columns = [name for name in source_names if name in destination_names]
    temporal = target_temporal_columns(cursor, table)
    if not pk:
        raise RuntimeError(f"No primary/natural key registered for dbo.{table}")
    if any(name not in columns for name in pk):
        raise RuntimeError(f"Key {pk} unavailable in dbo.{table}")

    source_rows = source.execute(
        "SELECT " + ",".join(q(name) for name in columns) + " FROM " + q(table)
    ).fetchall()
    for index, name in enumerate(columns):
        if name in temporal:
            source_rows = [tuple(
                coerce_temporal(value, temporal[name]) if position == index else value
                for position, value in enumerate(row)
            ) for row in source_rows]
    cursor.execute("SELECT " + ",".join(q(name) for name in columns) + " FROM dbo." + q(table))
    key_positions = [columns.index(name) for name in pk]
    existing = {tuple(row[index] for index in key_positions): tuple(row) for row in cursor.fetchall()}
    inserts, updates = [], []
    for row in source_rows:
        row = tuple(row)
        key = tuple(row[index] for index in key_positions)
        old = existing.get(key)
        if old is None:
            inserts.append(row)
        elif tuple(map(normalise, old)) != tuple(map(normalise, row)):
            updates.append(row)

    print(f"{table}: source={len(source_rows)} insert={len(inserts)} update={len(updates)} preserve_target_only={len(existing)-len(source_rows)+len(inserts)}")
    if not apply:
        return

    non_key_columns = [name for name in columns if name not in pk]
    if updates and non_key_columns:
        update_sql = "UPDATE dbo." + q(table) + " SET " + ",".join(q(name) + "=%s" for name in non_key_columns)
        update_sql += " WHERE " + " AND ".join(q(name) + "=%s" for name in pk)
        update_values = [tuple(row[columns.index(name)] for name in non_key_columns + list(pk)) for row in updates]
        cursor.executemany(update_sql, update_values)
    if inserts:
        identity = has_identity(cursor, table)
        if identity:
            cursor.execute("SET IDENTITY_INSERT dbo." + q(table) + " ON")
        try:
            # pymssql executemany sends rows one at a time. Batched VALUES
            # statements keep a large activity-log migration within a short
            # cutover window while remaining below SQL Server's 2100 parameter
            # limit.
            batch_size = max(1, min(100, 2000 // len(columns)))
            prefix = "INSERT INTO dbo." + q(table) + " (" + ",".join(q(name) for name in columns) + ") VALUES "
            values_sql = "(" + ",".join("%s" for _ in columns) + ")"
            for start in range(0, len(inserts), batch_size):
                batch = inserts[start:start + batch_size]
                cursor.execute(prefix + ",".join(values_sql for _ in batch), tuple(value for row in batch for value in row))
        finally:
            if identity:
                cursor.execute("SET IDENTITY_INSERT dbo." + q(table) + " OFF")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", default="instance/sec_app.sqlite3", help="SQLite snapshot path")
    parser.add_argument("--apply", action="store_true", help="perform insert/update changes")
    args = parser.parse_args()
    source_path = Path(args.source).resolve()
    if not source_path.is_file():
        raise SystemExit("SQLite source tidak ditemukan: " + str(source_path))
    source = sqlite3.connect(source_path)
    target = target_connection()
    try:
        cursor = target.cursor()
        cursor.execute("SELECT DB_NAME()")
        print("TARGET", cursor.fetchone()[0], "MODE", "APPLY" if args.apply else "DRY-RUN")
        ensure_compatibility_columns(cursor, source)
        for table in dependency_order(source, sqlite_tables(source)):
            sync_table(source, cursor, table, args.apply)
        if args.apply:
            target.commit()
            print("MIGRATION COMMITTED")
        else:
            target.rollback()
            print("NO CHANGES MADE")
    except Exception:
        target.rollback()
        raise
    finally:
        source.close()
        target.close()


if __name__ == "__main__":
    main()
