"""Persistent storage for the shared BlackOwl organization structure."""

import json

from app.database.db import get_connection, is_sqlite

DEFAULT_STRUCTURE = {
    "head": "Head of IT Security",
    "teams": [{"id": "appsec", "name": "Application Security", "lead": "", "members": []}],
}
_table_ready = False


def _ensure_table():
    global _table_ready
    if _table_ready:
        return
    if is_sqlite():
        _table_ready = True
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        IF OBJECT_ID('dbo.blackowl_organization', 'U') IS NULL
        CREATE TABLE dbo.blackowl_organization (
            id TINYINT NOT NULL PRIMARY KEY,
            structure_json NVARCHAR(MAX) NOT NULL,
            updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
            updated_by INT NULL
        )
    """)
    conn.commit()
    conn.close()
    _table_ready = True


def get_organization():
    _ensure_table()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT structure_json FROM dbo.blackowl_organization WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if not row:
        return DEFAULT_STRUCTURE
    try:
        return json.loads(row.structure_json)
    except (TypeError, ValueError):
        return DEFAULT_STRUCTURE


def save_organization(structure, user_id=None):
    _ensure_table()
    payload = json.dumps(structure, ensure_ascii=False)
    conn = get_connection()
    cursor = conn.cursor()
    if is_sqlite():
        cursor.execute("""INSERT INTO blackowl_organization (id, structure_json, updated_at, updated_by)
            VALUES (1, ?, CURRENT_TIMESTAMP, ?)
            ON CONFLICT(id) DO UPDATE SET structure_json=excluded.structure_json,
            updated_at=CURRENT_TIMESTAMP, updated_by=excluded.updated_by""", (payload, user_id))
    else:
        cursor.execute("""
        MERGE dbo.blackowl_organization AS target
        USING (SELECT CAST(1 AS TINYINT) AS id) AS source ON target.id = source.id
        WHEN MATCHED THEN UPDATE SET structure_json = ?, updated_at = SYSUTCDATETIME(), updated_by = ?
        WHEN NOT MATCHED THEN INSERT (id, structure_json, updated_by) VALUES (1, ?, ?);
    """, (payload, user_id, payload, user_id))
    conn.commit()
    conn.close()
