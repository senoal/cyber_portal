"""Clone the SEC_APP table schema from one SQL Server database into an empty one.

Only schema metadata is read from the donor. No donor rows are copied and the
target must have no user tables, preventing accidental overwrite.
"""
import argparse
import os
import sqlite3

import pymssql


def q(name): return "[" + name.replace("]", "]]" ) + "]"


def connect(database):
    required = {key: os.getenv("SEC_APP_DB_" + key, "") for key in ("SERVER", "UID", "PASSWORD")}
    if not all(required.values()): raise SystemExit("Atur SEC_APP_DB_SERVER, _UID, dan _PASSWORD.")
    return pymssql.connect(server=required["SERVER"], port=int(os.getenv("SEC_APP_DB_PORT", "1433")), user=required["UID"], password=required["PASSWORD"], database=database, login_timeout=15, timeout=60, charset="UTF-8")


def sql_type(name, max_length, precision, scale):
    name = name.lower()
    if name in {"varchar", "char", "varbinary", "binary"}:
        return f"{name}({'MAX' if max_length == -1 else max_length})"
    if name in {"nvarchar", "nchar"}:
        return f"{name}({'MAX' if max_length == -1 else max_length // 2})"
    if name in {"decimal", "numeric"}: return f"{name}({precision},{scale})"
    if name in {"datetime2", "datetimeoffset", "time"}: return f"{name}({scale})"
    return name


def metadata_int(value):
    return int.from_bytes(value, byteorder="little", signed=True) if isinstance(value, bytes) else int(value)


def donor_tables(conn, table_names):
    cur = conn.cursor()
    cur.execute("SELECT t.name FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id WHERE s.name='dbo'")
    available = {row[0] for row in cur.fetchall()}
    missing = set(table_names) - available
    if missing: raise RuntimeError("Tabel sumber tidak ditemukan: " + ", ".join(sorted(missing)))
    return sorted(table_names)


def create_table(donor, target, table):
    cur = donor.cursor()
    cur.execute("""
        SELECT c.column_id,c.name,ty.name,c.max_length,c.precision,c.scale,c.is_nullable,
               c.is_identity,ic.seed_value,ic.increment_value,dc.definition
        FROM sys.columns c
        JOIN sys.tables t ON t.object_id=c.object_id JOIN sys.schemas s ON s.schema_id=t.schema_id
        JOIN sys.types ty ON ty.user_type_id=c.user_type_id
        LEFT JOIN sys.identity_columns ic ON ic.object_id=c.object_id AND ic.column_id=c.column_id
        LEFT JOIN sys.default_constraints dc ON dc.parent_object_id=c.object_id AND dc.parent_column_id=c.column_id
        WHERE s.name='dbo' AND t.name=%s ORDER BY c.column_id
    """, (table,))
    columns = cur.fetchall(); definitions=[]
    for _, name, typ, length, precision, scale, nullable, identity, seed, increment, default in columns:
        definition = q(name) + " " + sql_type(typ, length, precision, scale)
        if identity: definition += f" IDENTITY({metadata_int(seed)},{metadata_int(increment)})"
        if default: definition += " DEFAULT " + default
        definition += " NULL" if nullable else " NOT NULL"
        definitions.append(definition)
    target.cursor().execute("CREATE TABLE dbo." + q(table) + " (" + ", ".join(definitions) + ")")


def add_primary_and_foreign_keys(donor, target, tables):
    cur = donor.cursor(); out = target.cursor()
    for table in tables:
        cur.execute("""
            SELECT kc.name,i.type_desc,ic.key_ordinal,c.name
            FROM sys.key_constraints kc JOIN sys.tables t ON t.object_id=kc.parent_object_id
            JOIN sys.schemas s ON s.schema_id=t.schema_id JOIN sys.indexes i ON i.object_id=t.object_id AND i.index_id=kc.unique_index_id
            JOIN sys.index_columns ic ON ic.object_id=i.object_id AND ic.index_id=i.index_id
            JOIN sys.columns c ON c.object_id=t.object_id AND c.column_id=ic.column_id
            WHERE s.name='dbo' AND t.name=%s AND kc.type='PK' ORDER BY ic.key_ordinal
        """, (table,))
        rows=cur.fetchall()
        if rows:
            out.execute("ALTER TABLE dbo."+q(table)+" ADD CONSTRAINT "+q(rows[0][0])+" PRIMARY KEY "+rows[0][1].replace('_',' ')+" ("+','.join(q(r[3]) for r in rows)+")")
    cur.execute("""
        SELECT fk.name,ct.name,rt.name,fkc.constraint_column_id,cc.name,rc.name,
               fk.delete_referential_action_desc,fk.update_referential_action_desc
        FROM sys.foreign_keys fk JOIN sys.tables ct ON ct.object_id=fk.parent_object_id JOIN sys.schemas cs ON cs.schema_id=ct.schema_id
        JOIN sys.tables rt ON rt.object_id=fk.referenced_object_id
        JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id=fk.object_id
        JOIN sys.columns cc ON cc.object_id=ct.object_id AND cc.column_id=fkc.parent_column_id
        JOIN sys.columns rc ON rc.object_id=rt.object_id AND rc.column_id=fkc.referenced_column_id
        WHERE cs.name='dbo' ORDER BY fk.name,fkc.constraint_column_id
    """)
    groups={}
    for name, child, parent, _, child_col, parent_col, on_delete, on_update in cur.fetchall():
        if child not in tables or parent not in tables: continue
        item=groups.setdefault(name,[child,parent,[],[],on_delete.replace('_',' '),on_update.replace('_',' ')])
        item[2].append(child_col); item[3].append(parent_col)
    for name,(child,parent,children,parents,on_delete,on_update) in groups.items():
        out.execute("ALTER TABLE dbo."+q(child)+" ADD CONSTRAINT "+q(name)+" FOREIGN KEY ("+','.join(q(v) for v in children)+") REFERENCES dbo."+q(parent)+" ("+','.join(q(v) for v in parents)+") ON DELETE "+on_delete+" ON UPDATE "+on_update)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--donor', default='SEC_PORTAL')
    parser.add_argument('--target', default=os.getenv('SEC_APP_DB_DATABASE', ''))
    parser.add_argument('--sqlite-source', default='instance/sec_app.sqlite3')
    args=parser.parse_args()
    if not args.target: raise SystemExit('Tentukan --target atau SEC_APP_DB_DATABASE.')
    with sqlite3.connect(args.sqlite_source) as source:
        names=[row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    donor=connect(args.donor); target=connect(args.target)
    try:
        check=target.cursor(); check.execute("SELECT COUNT(*) FROM sys.tables WHERE is_ms_shipped=0")
        if check.fetchone()[0]: raise RuntimeError('Target tidak kosong; bootstrap dibatalkan.')
        tables=donor_tables(donor,names)
        for table in tables: create_table(donor,target,table)
        add_primary_and_foreign_keys(donor,target,tables)
        target.commit(); print('SCHEMA CREATED:',len(tables),'tables')
    except Exception:
        target.rollback(); raise
    finally:
        donor.close(); target.close()


if __name__=='__main__': main()
