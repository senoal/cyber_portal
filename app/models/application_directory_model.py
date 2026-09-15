"""Persistence for the application directory and its usage guides."""

from app.database.db import get_connection, is_sqlite


_ready = False


def ensure_application_directory_tables():
    global _ready
    if _ready:
        return
    if is_sqlite():
        # The application now runs on SQLite.  The old implementation skipped
        # the SQL Server DDL in this branch, but did not create an equivalent
        # local schema.  As a result, the add form could be displayed while
        # its first save failed with "no such table".
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS application_directory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    ip TEXT,
                    purpose TEXT,
                    access_info TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS application_directory_modules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    application_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    sort_order INTEGER NOT NULL,
                    FOREIGN KEY (application_id) REFERENCES application_directory(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS application_directory_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    module_id INTEGER NOT NULL,
                    instruction TEXT NOT NULL,
                    sort_order INTEGER NOT NULL,
                    FOREIGN KEY (module_id) REFERENCES application_directory_modules(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS application_directory_step_images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    step_id INTEGER NOT NULL,
                    file_name TEXT NOT NULL,
                    sort_order INTEGER NOT NULL,
                    FOREIGN KEY (step_id) REFERENCES application_directory_steps(id) ON DELETE CASCADE
                )
            """)
            conn.commit()
        finally:
            conn.close()
        _ready = True
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        IF OBJECT_ID('dbo.application_directory', 'U') IS NULL
        CREATE TABLE dbo.application_directory (
            id INT IDENTITY(1,1) PRIMARY KEY,
            name NVARCHAR(200) NOT NULL,
            ip NVARCHAR(100) NULL,
            purpose NVARCHAR(MAX) NULL,
            access_info NVARCHAR(MAX) NULL,
            created_at DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
            updated_at DATETIME2 NOT NULL DEFAULT SYSDATETIME()
        );
        IF OBJECT_ID('dbo.application_directory_modules', 'U') IS NULL
        CREATE TABLE dbo.application_directory_modules (
            id INT IDENTITY(1,1) PRIMARY KEY,
            application_id INT NOT NULL,
            name NVARCHAR(200) NOT NULL,
            sort_order INT NOT NULL,
            CONSTRAINT FK_app_directory_modules_application FOREIGN KEY (application_id)
                REFERENCES dbo.application_directory(id) ON DELETE CASCADE
        );
        IF OBJECT_ID('dbo.application_directory_steps', 'U') IS NULL
        CREATE TABLE dbo.application_directory_steps (
            id INT IDENTITY(1,1) PRIMARY KEY,
            module_id INT NOT NULL,
            instruction NVARCHAR(MAX) NOT NULL,
            sort_order INT NOT NULL,
            CONSTRAINT FK_app_directory_steps_module FOREIGN KEY (module_id)
                REFERENCES dbo.application_directory_modules(id) ON DELETE CASCADE
        );
        IF OBJECT_ID('dbo.application_directory_step_images', 'U') IS NULL
        CREATE TABLE dbo.application_directory_step_images (
            id INT IDENTITY(1,1) PRIMARY KEY,
            step_id INT NOT NULL,
            file_name NVARCHAR(260) NOT NULL,
            sort_order INT NOT NULL,
            CONSTRAINT FK_app_directory_images_step FOREIGN KEY (step_id)
                REFERENCES dbo.application_directory_steps(id) ON DELETE CASCADE
        );
    """)
    conn.commit()
    conn.close()
    _ready = True


def list_applications():
    ensure_application_directory_tables()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, a.name, a.ip, a.purpose, a.access_info, a.created_at,
               COUNT(DISTINCT m.id) AS module_count
        FROM dbo.application_directory a
        LEFT JOIN dbo.application_directory_modules m ON m.application_id = a.id
        GROUP BY a.id, a.name, a.ip, a.purpose, a.access_info, a.created_at
        ORDER BY a.name
    """)
    rows = [dict(zip([c[0] for c in cursor.description], row)) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_application(application_id):
    ensure_application_directory_tables()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, ip, purpose, access_info, created_at, updated_at FROM dbo.application_directory WHERE id = ?", (application_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    application = dict(zip([c[0] for c in cursor.description], row))
    cursor.execute("SELECT id, name, sort_order FROM dbo.application_directory_modules WHERE application_id = ? ORDER BY sort_order, id", (application_id,))
    modules = []
    for module_row in cursor.fetchall():
        module = {"id": module_row.id, "name": module_row.name, "sort_order": module_row.sort_order, "steps": []}
        cursor.execute("SELECT id, instruction, sort_order FROM dbo.application_directory_steps WHERE module_id = ? ORDER BY sort_order, id", (module_row.id,))
        for step_row in cursor.fetchall():
            cursor.execute("SELECT id, file_name, sort_order FROM dbo.application_directory_step_images WHERE step_id = ? ORDER BY sort_order, id", (step_row.id,))
            images = [dict(zip([c[0] for c in cursor.description], image)) for image in cursor.fetchall()]
            module["steps"].append({"id": step_row.id, "instruction": step_row.instruction, "sort_order": step_row.sort_order, "images": images})
        modules.append(module)
    conn.close()
    application["modules"] = modules
    return application


def save_application(data, application_id=None):
    """Create/update a record. Returns its id and image names replaced on update."""
    ensure_application_directory_tables()
    conn = get_connection()
    cursor = conn.cursor()
    removed_images = []
    try:
        if application_id is None:
            # Existing local database snapshots have non-null timestamp
            # columns without DEFAULT values.  Set them explicitly so adding
            # an application works with both those snapshots and new ones.
            cursor.execute("""INSERT INTO dbo.application_directory
                              (name, ip, purpose, access_info, created_at, updated_at)
                              OUTPUT INSERTED.id VALUES (?, ?, ?, ?, SYSDATETIME(), SYSDATETIME())""",
                           (data["name"], data["ip"], data["purpose"], data["access_info"]))
            application_id = cursor.fetchone()[0]
        else:
            cursor.execute("""SELECT i.file_name FROM dbo.application_directory_step_images i
                              JOIN dbo.application_directory_steps s ON s.id=i.step_id
                              JOIN dbo.application_directory_modules m ON m.id=s.module_id
                              WHERE m.application_id=?""", (application_id,))
            removed_images = [row.file_name for row in cursor.fetchall()]
            cursor.execute("UPDATE dbo.application_directory SET name=?, ip=?, purpose=?, access_info=?, updated_at=SYSDATETIME() WHERE id=?", (data["name"], data["ip"], data["purpose"], data["access_info"], application_id))
            cursor.execute("DELETE FROM dbo.application_directory_modules WHERE application_id=?", (application_id,))
        for module_order, module in enumerate(data["modules"], 1):
            cursor.execute("INSERT INTO dbo.application_directory_modules (application_id, name, sort_order) OUTPUT INSERTED.id VALUES (?, ?, ?)", (application_id, module["name"], module_order))
            module_id = cursor.fetchone()[0]
            for step_order, step in enumerate(module["steps"], 1):
                cursor.execute("INSERT INTO dbo.application_directory_steps (module_id, instruction, sort_order) OUTPUT INSERTED.id VALUES (?, ?, ?)", (module_id, step["instruction"], step_order))
                step_id = cursor.fetchone()[0]
                for image_order, file_name in enumerate(step.get("images", []), 1):
                    cursor.execute("INSERT INTO dbo.application_directory_step_images (step_id, file_name, sort_order) VALUES (?, ?, ?)", (step_id, file_name, image_order))
        conn.commit()
        return application_id, removed_images
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_application(application_id):
    application = get_application(application_id)
    if not application:
        return []
    images = [image["file_name"] for module in application["modules"] for step in module["steps"] for image in step["images"]]
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM dbo.application_directory WHERE id=?", (application_id,))
    conn.commit()
    conn.close()
    return images
