"""Create a local SQLite snapshot from MSSQL without changing the source DB.

Run only with a dedicated READ-ONLY MSSQL account. The target must not exist;
this prevents an accidental overwrite of a useful local database.
"""
import argparse
import os
import sqlite3
from pathlib import Path
import pyodbc

TYPE_MAP = {
    "bigint": "INTEGER", "int": "INTEGER", "smallint": "INTEGER", "tinyint": "INTEGER",
    "bit": "INTEGER", "decimal": "NUMERIC", "numeric": "NUMERIC", "float": "REAL",
    "real": "REAL", "money": "NUMERIC", "smallmoney": "NUMERIC", "date": "TEXT",
    "datetime": "TEXT", "datetime2": "TEXT", "datetimeoffset": "TEXT", "time": "TEXT",
    "binary": "BLOB", "varbinary": "BLOB", "image": "BLOB",
}

LOCAL_COMPATIBILITY_COLUMNS = {
    # Present in the application but absent from this production snapshot.
    # Keep it local so a snapshot never mutates production schema.
    "pentest_tasks": {"manual_owner_name": "TEXT"},
}

def q(name): return '"' + name.replace('"', '""') + '"'

def source_connection():
    keys = {key: os.getenv("SEC_APP_DB_" + key, "") for key in ("SERVER", "DATABASE", "UID", "PASSWORD")}
    if not all(keys.values()):
        raise SystemExit("Set SEC_APP_DB_SERVER, _DATABASE, _UID, dan _PASSWORD untuk akun MSSQL read-only.")
    driver = os.getenv("SEC_APP_DB_DRIVER", "{ODBC Driver 18 for SQL Server}")
    encrypt = os.getenv("SEC_APP_DB_ENCRYPT", "yes")
    trust = os.getenv("SEC_APP_DB_TRUST_SERVER_CERTIFICATE", "no")
    # Keep this equivalent to the successful ODBC administrator test.  Read
    # operations below are SELECT-only; do not require ApplicationIntent,
    # because older production instances may not support it.
    return pyodbc.connect(f"DRIVER={driver};SERVER={keys['SERVER']};DATABASE={keys['DATABASE']};UID={keys['UID']};PWD={keys['PASSWORD']};Encrypt={encrypt};TrustServerCertificate={trust}")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="path SQLite baru, contoh app/instance/sec_app.sqlite3")
    args = parser.parse_args(); target = Path(args.target).resolve()
    if target.exists(): raise SystemExit(f"Target sudah ada dan tidak diubah: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    src = source_connection(); dst = sqlite3.connect(target)
    try:
        dst.execute("PRAGMA foreign_keys = OFF")
        tables = src.cursor(); tables.execute("SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' AND TABLE_SCHEMA NOT IN ('sys','INFORMATION_SCHEMA') ORDER BY TABLE_SCHEMA,TABLE_NAME")
        table_names = tables.fetchall()
        for schema, table in table_names:
            cur = src.cursor(); cur.execute("SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=? AND TABLE_NAME=? ORDER BY ORDINAL_POSITION", schema, table)
            columns = cur.fetchall()
            pk = src.cursor(); pk.execute("SELECT k.COLUMN_NAME FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS t JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE k ON t.CONSTRAINT_NAME=k.CONSTRAINT_NAME AND t.TABLE_SCHEMA=k.TABLE_SCHEMA WHERE t.CONSTRAINT_TYPE='PRIMARY KEY' AND t.TABLE_SCHEMA=? AND t.TABLE_NAME=? ORDER BY k.ORDINAL_POSITION", schema, table)
            primary = [r[0] for r in pk.fetchall()]
            definitions = []
            for name, data_type, nullable, default in columns:
                typ = TYPE_MAP.get(data_type.lower(), "TEXT")
                suffix = " NOT NULL" if nullable == "NO" else ""
                if len(primary) == 1 and name == primary[0] and typ == "INTEGER": suffix += " PRIMARY KEY"
                definitions.append(q(name) + " " + typ + suffix)
            if len(primary) > 1: definitions.append("PRIMARY KEY (" + ", ".join(q(v) for v in primary) + ")")
            foreign = src.cursor(); foreign.execute("""
                SELECT fk.name, fkc.constraint_column_id, pc.name, ps.name, pt.name, rc.name
                FROM sys.foreign_key_columns fkc
                JOIN sys.foreign_keys fk ON fk.object_id=fkc.constraint_object_id
                JOIN sys.tables ct ON ct.object_id=fkc.parent_object_id
                JOIN sys.schemas cs ON cs.schema_id=ct.schema_id
                JOIN sys.columns pc ON pc.object_id=ct.object_id AND pc.column_id=fkc.parent_column_id
                JOIN sys.tables pt ON pt.object_id=fkc.referenced_object_id
                JOIN sys.schemas ps ON ps.schema_id=pt.schema_id
                JOIN sys.columns rc ON rc.object_id=pt.object_id AND rc.column_id=fkc.referenced_column_id
                WHERE cs.name=? AND ct.name=? ORDER BY fk.name, fkc.constraint_column_id
            """, schema, table)
            grouped = {}
            for fk_name, _, child, parent_schema, parent_table, parent in foreign.fetchall():
                item = grouped.setdefault(fk_name, [[], parent_schema, parent_table, []])
                item[0].append(child); item[3].append(parent)
            for child, _, parent_table, parent in grouped.values():
                # SQLite has no schemas; production databases normally use dbo.
                definitions.append("FOREIGN KEY (" + ", ".join(q(v) for v in child) + ") REFERENCES " + q(parent_table) + " (" + ", ".join(q(v) for v in parent) + ")")
            dst.execute("CREATE TABLE " + q(table) + " (" + ", ".join(definitions) + ")")
            names = [r[0] for r in columns]
            data = src.cursor(); data.execute("SELECT * FROM " + q(schema) + "." + q(table))
            placeholders = ",".join("?" for _ in names)
            count = 0
            while True:
                batch = data.fetchmany(500)
                if not batch: break
                dst.executemany("INSERT INTO " + q(table) + " (" + ",".join(q(n) for n in names) + ") VALUES (" + placeholders + ")", batch); count += len(batch)
            source_count = src.cursor(); source_count.execute("SELECT COUNT(*) FROM " + q(schema) + "." + q(table))
            if source_count.fetchone()[0] != count: raise RuntimeError(f"Jumlah data tidak cocok: {schema}.{table}")
            print(f"OK {schema}.{table}: {count} rows")
        for table, columns in LOCAL_COMPATIBILITY_COLUMNS.items():
            if dst.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                current = {row[1] for row in dst.execute("PRAGMA table_info(" + q(table) + ")")}
                for name, data_type in columns.items():
                    if name not in current:
                        dst.execute("ALTER TABLE " + q(table) + " ADD COLUMN " + q(name) + " " + data_type)
                        print(f"Added local compatibility column: {table}.{name}")
        dst.execute("PRAGMA foreign_keys = ON"); dst.commit()
        violations = dst.execute("PRAGMA foreign_key_check").fetchall()
        if violations: raise RuntimeError(f"Foreign key tidak valid: {violations[:5]}")
        print(f"Migrasi selesai: {target}")
    except Exception:
        dst.close(); target.unlink(missing_ok=True); raise
    finally:
        try: src.close()
        except Exception: pass
        try: dst.close()
        except Exception: pass

if __name__ == "__main__": main()
