"""SQL Server persistence for the Tasks workspace."""

from datetime import date, datetime
import sqlite3
from time import sleep

from app.database.db import get_connection, is_sqlite


_ready = False


def _row(cursor, row):
    if row is None:
        return None
    return dict(zip([column[0] for column in cursor.description], row))


def _rows(cursor):
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _json_value(value):
    return value.isoformat() if isinstance(value, (datetime, date)) else value


def serialize(record):
    return {key: _json_value(value) for key, value in record.items()}


def ensure_tables():
    global _ready
    if _ready:
        return
    if is_sqlite():
        # SQLite deployments do not run the SQL Server migration scripts.
        # Create the Tasks schema safely on first use, preserving existing data.
        conn = get_connection(); cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          owner_id INTEGER NOT NULL,
          title TEXT NOT NULL,
          description TEXT NOT NULL DEFAULT '',
          category TEXT NOT NULL DEFAULT 'Personal',
          due_date TEXT NULL,
          priority TEXT NOT NULL DEFAULT 'medium' CHECK (priority IN ('low','medium','high')),
          completed INTEGER NOT NULL DEFAULT 0,
          canceled INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_attachments (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          task_id INTEGER NOT NULL,
          original_name TEXT NOT NULL,
          stored_name TEXT NOT NULL UNIQUE,
          size INTEGER NOT NULL,
          uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_subtasks (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          task_id INTEGER NOT NULL,
          name TEXT NOT NULL,
          due_date TEXT NULL,
          notes TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_subtask_attachments (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          subtask_id INTEGER NOT NULL,
          original_name TEXT NOT NULL,
          stored_name TEXT NOT NULL UNIQUE,
          size INTEGER NOT NULL,
          uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY (subtask_id) REFERENCES task_subtasks(id) ON DELETE CASCADE
        )
        """)
        # Foreign keys do not automatically create indexes in SQLite.  These
        # lookups back every Task/Step detail request, so without them the
        # cost grows with every step and attachment in the workspace.
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_tasks_owner_created ON tasks (owner_id, created_at DESC, id DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_task_attachments_task_id ON task_attachments (task_id, id DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_task_subtasks_task_due ON task_subtasks (task_id, due_date, id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_subtask_attachments_subtask_id ON task_subtask_attachments (subtask_id, id DESC)")
        conn.commit(); conn.close()
        _ready = True
        return
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("""
    IF OBJECT_ID('dbo.tasks', 'U') IS NULL
    CREATE TABLE dbo.tasks (
      id INT IDENTITY(1,1) PRIMARY KEY, owner_id INT NOT NULL,
      title NVARCHAR(120) NOT NULL, description NVARCHAR(MAX) NOT NULL DEFAULT '',
      category NVARCHAR(50) NOT NULL DEFAULT 'Personal', due_date DATE NULL,
      priority VARCHAR(10) NOT NULL DEFAULT 'medium', completed BIT NOT NULL DEFAULT 0,
      canceled BIT NOT NULL DEFAULT 0, created_at DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
      CONSTRAINT CK_tasks_priority CHECK (priority IN ('low','medium','high'))
    );
    IF OBJECT_ID('dbo.task_attachments', 'U') IS NULL
    CREATE TABLE dbo.task_attachments (
      id INT IDENTITY(1,1) PRIMARY KEY, task_id INT NOT NULL,
      original_name NVARCHAR(260) NOT NULL, stored_name NVARCHAR(260) NOT NULL UNIQUE,
      size BIGINT NOT NULL, uploaded_at DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
      CONSTRAINT FK_task_attachments_task FOREIGN KEY (task_id) REFERENCES dbo.tasks(id) ON DELETE CASCADE
    );
    IF OBJECT_ID('dbo.task_subtasks', 'U') IS NULL
    CREATE TABLE dbo.task_subtasks (
      id INT IDENTITY(1,1) PRIMARY KEY, task_id INT NOT NULL, name NVARCHAR(120) NOT NULL,
      due_date DATE NULL, notes NVARCHAR(500) NOT NULL DEFAULT '',
      created_at DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
      CONSTRAINT FK_task_subtasks_task FOREIGN KEY (task_id) REFERENCES dbo.tasks(id) ON DELETE CASCADE
    );
    IF OBJECT_ID('dbo.task_subtask_attachments', 'U') IS NULL
    CREATE TABLE dbo.task_subtask_attachments (
      id INT IDENTITY(1,1) PRIMARY KEY, subtask_id INT NOT NULL,
      original_name NVARCHAR(260) NOT NULL, stored_name NVARCHAR(260) NOT NULL UNIQUE,
      size BIGINT NOT NULL, uploaded_at DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
      CONSTRAINT FK_task_subtask_attachments_subtask FOREIGN KEY (subtask_id) REFERENCES dbo.task_subtasks(id) ON DELETE CASCADE
    );
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_tasks_owner_created' AND object_id = OBJECT_ID('dbo.tasks'))
      CREATE INDEX IX_tasks_owner_created ON dbo.tasks (owner_id, created_at DESC, id DESC);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_task_attachments_task_id' AND object_id = OBJECT_ID('dbo.task_attachments'))
      CREATE INDEX IX_task_attachments_task_id ON dbo.task_attachments (task_id, id DESC);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_task_subtasks_task_due' AND object_id = OBJECT_ID('dbo.task_subtasks'))
      CREATE INDEX IX_task_subtasks_task_due ON dbo.task_subtasks (task_id, due_date, id);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_subtask_attachments_subtask_id' AND object_id = OBJECT_ID('dbo.task_subtask_attachments'))
      CREATE INDEX IX_subtask_attachments_subtask_id ON dbo.task_subtask_attachments (subtask_id, id DESC);
    """)
    conn.commit(); conn.close(); _ready = True


def task_where(owner_id, status, search, date_from, date_to):
    clauses, params = ["owner_id = ?"], [owner_id]
    if status == 'active': clauses.extend(["completed = 0", "canceled = 0", "(due_date IS NULL OR due_date >= CAST(GETDATE() AS DATE))"])
    elif status == 'completed': clauses.extend(["completed = 1", "canceled = 0"])
    elif status == 'canceled': clauses.append("canceled = 1")
    elif status == 'deadline': clauses.extend(["completed = 0", "canceled = 0", "due_date IS NOT NULL", "due_date <= CAST(GETDATE() AS DATE)"])
    if search:
        clauses.append("(title LIKE ? OR description LIKE ? OR category LIKE ?)"); params.extend([f'%{search}%'] * 3)
    if date_from: clauses.append("due_date >= ?"); params.append(date_from)
    if date_to: clauses.append("due_date <= ?"); params.append(date_to)
    return " WHERE " + " AND ".join(clauses), params


def list_tasks(owner_id, status='all', search='', date_from='', date_to='', page=1, per_page=5):
    ensure_tables(); where, params = task_where(owner_id, status, search, date_from, date_to)
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM dbo.tasks" + where, params); total = cursor.fetchone()[0]
    cursor.execute("SELECT * FROM dbo.tasks" + where + " ORDER BY created_at DESC, id DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY", [*params, (page - 1) * per_page, per_page])
    records = _rows(cursor); conn.close(); return records, total


def get_task(owner_id, task_id):
    ensure_tables(); conn = get_connection(); cursor = conn.cursor()
    cursor.execute("SELECT * FROM dbo.tasks WHERE id=? AND owner_id=?", (task_id, owner_id)); task = _row(cursor, cursor.fetchone())
    if not task: conn.close(); return None
    cursor.execute("SELECT id, original_name, size, uploaded_at FROM dbo.task_attachments WHERE task_id=? ORDER BY id DESC", (task_id,)); task['attachments'] = _rows(cursor)
    cursor.execute("SELECT * FROM dbo.task_subtasks WHERE task_id=? ORDER BY CASE WHEN due_date IS NULL THEN 1 ELSE 0 END, due_date, id", (task_id,)); task['subtasks'] = _rows(cursor)
    conn.close(); return task


def insert_task(owner_id, data):
    ensure_tables()
    # SQLite has one writer. A dashboard/audit request can briefly hold that
    # writer lock, so retry only this short, atomic save operation before
    # reporting a real database failure to the user.
    for attempt in range(4):
        conn = None
        try:
            conn = get_connection(); cursor = conn.cursor()
            if is_sqlite():
                # Earlier SQLite deployments created these status/timestamp
                # columns as NOT NULL without defaults. Supply their initial
                # values explicitly so both old and current schemas can save.
                cursor.execute("""INSERT INTO tasks
                                  (owner_id,title,description,category,due_date,priority,completed,canceled,created_at)
                                  VALUES (?,?,?,?,?,?,0,0,CURRENT_TIMESTAMP)""",
                               (owner_id, data['title'], data['description'], data['category'], data['due_date'], data['priority']))
                task_id = cursor.lastrowid
            else:
                cursor.execute("""INSERT INTO dbo.tasks (owner_id,title,description,category,due_date,priority)
                                  OUTPUT INSERTED.id VALUES (?,?,?,?,?,?)""", (owner_id, data['title'], data['description'], data['category'], data['due_date'], data['priority']))
                task_id = cursor.fetchone()[0]
            conn.commit()
            conn.close()
            conn = None
            return get_task(owner_id, task_id)
        except sqlite3.OperationalError as error:
            if conn:
                conn.rollback(); conn.close()
            if "locked" not in str(error).lower() or attempt == 3:
                raise
            sleep(0.25 * (attempt + 1))
        except Exception:
            if conn:
                conn.rollback(); conn.close()
            raise


def update_task(owner_id, task_id, updates):
    ensure_tables(); allowed = ('title','description','category','due_date','priority','completed','canceled')
    updates = {key: value for key, value in updates.items() if key in allowed}
    if not updates: return None
    if updates.get('completed'): updates['canceled'] = False
    if updates.get('canceled'): updates['completed'] = False
    clause = ', '.join(f'{key} = ?' for key in updates)
    conn = get_connection(); cursor = conn.cursor(); cursor.execute(f"UPDATE dbo.tasks SET {clause} WHERE id=? AND owner_id=?", [*updates.values(), task_id, owner_id]); found = cursor.rowcount; conn.commit(); conn.close()
    return get_task(owner_id, task_id) if found else None


def delete_task(owner_id, task_id):
    task = get_task(owner_id, task_id)
    if not task: return None
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("SELECT a.stored_name FROM dbo.task_subtask_attachments a JOIN dbo.task_subtasks s ON s.id=a.subtask_id WHERE s.task_id=?", (task_id,)); sub_files = [row[0] for row in cursor.fetchall()]
    cursor.execute("SELECT stored_name FROM dbo.task_attachments WHERE task_id=?", (task_id,)); files = [row[0] for row in cursor.fetchall()] + sub_files
    cursor.execute("DELETE FROM dbo.tasks WHERE id=? AND owner_id=?", (task_id, owner_id)); conn.commit(); conn.close(); return files


def stats(owner_id, search='', date_from='', date_to=''):
    ensure_tables(); where, params = task_where(owner_id, 'all', search, date_from, date_to)
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("""SELECT COUNT(*),
        SUM(CASE WHEN completed=1 AND canceled=0 THEN 1 ELSE 0 END),
        SUM(CASE WHEN canceled=1 THEN 1 ELSE 0 END),
        SUM(CASE WHEN completed=0 AND canceled=0 AND due_date=CAST(GETDATE() AS DATE) THEN 1 ELSE 0 END),
        SUM(CASE WHEN completed=0 AND canceled=0 AND due_date<CAST(GETDATE() AS DATE) THEN 1 ELSE 0 END)
        FROM dbo.tasks""" + where, params)
    total, completed, canceled, due_today, overdue = cursor.fetchone(); conn.close()
    completed, canceled, due_today, overdue = completed or 0, canceled or 0, due_today or 0, overdue or 0
    # These dashboard states must not overlap: an overdue task needs attention
    # in Deadline, rather than inflating the Active Queue count.
    return {'total': total, 'completed': completed, 'canceled': canceled, 'active': total-completed-canceled-overdue, 'due_today': due_today, 'overdue': overdue}


def add_attachment(owner_id, task_id, original_name, stored_name, size, subtask_id=None):
    ensure_tables(); conn = get_connection(); cursor = conn.cursor()
    if subtask_id is None:
        cursor.execute("SELECT 1 FROM dbo.tasks WHERE id=? AND owner_id=?", (task_id, owner_id)); table, foreign = 'dbo.task_attachments', 'task_id'
    else:
        cursor.execute("SELECT 1 FROM dbo.task_subtasks s JOIN dbo.tasks t ON t.id=s.task_id WHERE s.id=? AND s.task_id=? AND t.owner_id=?", (subtask_id, task_id, owner_id)); table, foreign = 'dbo.task_subtask_attachments', 'subtask_id'
    if not cursor.fetchone(): conn.close(); return None
    parent_id = task_id if subtask_id is None else subtask_id
    if is_sqlite():
        cursor.execute(f"INSERT INTO {table} ({foreign},original_name,stored_name,size,uploaded_at) VALUES (?,?,?,?,CURRENT_TIMESTAMP)", (parent_id, original_name, stored_name, size))
        attachment_id = cursor.lastrowid
    else:
        cursor.execute(f"INSERT INTO {table} ({foreign},original_name,stored_name,size) OUTPUT INSERTED.id VALUES (?,?,?,?)", (parent_id, original_name, stored_name, size)); attachment_id = cursor.fetchone()[0]
    conn.commit(); conn.close(); return attachment_id


def attachment(owner_id, attachment_id, subtask=False):
    ensure_tables(); conn = get_connection(); cursor = conn.cursor()
    if subtask:
        cursor.execute("SELECT a.id,a.original_name,a.stored_name FROM dbo.task_subtask_attachments a JOIN dbo.task_subtasks s ON s.id=a.subtask_id JOIN dbo.tasks t ON t.id=s.task_id WHERE a.id=? AND t.owner_id=?", (attachment_id, owner_id))
    else:
        cursor.execute("SELECT a.id,a.original_name,a.stored_name FROM dbo.task_attachments a JOIN dbo.tasks t ON t.id=a.task_id WHERE a.id=? AND t.owner_id=?", (attachment_id, owner_id))
    item = _row(cursor, cursor.fetchone()); conn.close(); return item


def delete_attachment(owner_id, attachment_id, subtask=False):
    item = attachment(owner_id, attachment_id, subtask)
    if not item: return None
    conn = get_connection(); cursor = conn.cursor(); cursor.execute(f"DELETE FROM {'dbo.task_subtask_attachments' if subtask else 'dbo.task_attachments'} WHERE id=?", (attachment_id,)); conn.commit(); conn.close(); return item['stored_name']


def get_subtask(owner_id, task_id, subtask_id):
    ensure_tables(); conn = get_connection(); cursor = conn.cursor()
    cursor.execute("SELECT s.* FROM dbo.task_subtasks s JOIN dbo.tasks t ON t.id=s.task_id WHERE s.id=? AND s.task_id=? AND t.owner_id=?", (subtask_id, task_id, owner_id)); subtask = _row(cursor, cursor.fetchone())
    if subtask:
        cursor.execute("SELECT id,original_name,size,uploaded_at FROM dbo.task_subtask_attachments WHERE subtask_id=? ORDER BY id DESC", (subtask_id,)); subtask['attachments'] = _rows(cursor)
    conn.close(); return subtask


def save_subtask(owner_id, task_id, data, subtask_id=None):
    ensure_tables()
    if is_sqlite():
        # Acquire SQLite's single writer before checking the parent task. This
        # makes a Step save one short transaction instead of an open read that
        # later competes with another request for the writer lock.
        for attempt in range(3):
            conn = None
            try:
                conn = get_connection(); cursor = conn.cursor(); cursor.execute("BEGIN IMMEDIATE")
                cursor.execute("SELECT 1 FROM tasks WHERE id=? AND owner_id=?", (task_id, owner_id))
                if not cursor.fetchone(): conn.rollback(); conn.close(); return None
                if subtask_id is None:
                    cursor.execute("""INSERT INTO task_subtasks (task_id,name,due_date,notes,created_at)
                                      VALUES (?,?,?,?,CURRENT_TIMESTAMP)""",
                                   (task_id, data['name'], data['due_date'], data['notes']))
                    saved_id = cursor.lastrowid
                else:
                    cursor.execute("""UPDATE task_subtasks SET name=?, due_date=?, notes=?
                                      WHERE id=? AND task_id=? AND EXISTS
                                      (SELECT 1 FROM tasks t WHERE t.id=task_subtasks.task_id AND t.owner_id=?)""",
                                   (data['name'], data['due_date'], data['notes'], subtask_id, task_id, owner_id))
                    if not cursor.rowcount: conn.rollback(); conn.close(); return None
                    saved_id = subtask_id
                conn.commit(); conn.close(); return get_subtask(owner_id, task_id, saved_id)
            except sqlite3.OperationalError as error:
                if conn: conn.rollback(); conn.close()
                if "locked" not in str(error).lower() and "busy" not in str(error).lower(): raise
                if attempt == 2: raise
                sleep(.15 * (attempt + 1))
            except Exception:
                if conn: conn.rollback(); conn.close()
                raise

    conn = get_connection(); cursor = conn.cursor()
    if subtask_id is None:
        cursor.execute("SELECT 1 FROM dbo.tasks WHERE id=? AND owner_id=?", (task_id, owner_id))
        if not cursor.fetchone(): conn.close(); return None
        if is_sqlite():
            # Legacy SQLite tables require created_at explicitly.
            cursor.execute("""INSERT INTO task_subtasks (task_id,name,due_date,notes,created_at)
                              VALUES (?,?,?,?,CURRENT_TIMESTAMP)""",
                           (task_id, data['name'], data['due_date'], data['notes']))
            subtask_id = cursor.lastrowid
        else:
            cursor.execute("INSERT INTO dbo.task_subtasks (task_id,name,due_date,notes) OUTPUT INSERTED.id VALUES (?,?,?,?)", (task_id,data['name'],data['due_date'],data['notes'])); subtask_id=cursor.fetchone()[0]
    else:
        if is_sqlite():
            # SQLite has no SQL Server-style ``UPDATE alias ... FROM`` here.
            # Preserve the ownership guard with a correlated EXISTS predicate.
            cursor.execute("""UPDATE task_subtasks SET name=?, due_date=?, notes=?
                              WHERE id=? AND task_id=? AND EXISTS
                              (SELECT 1 FROM tasks t WHERE t.id=task_subtasks.task_id AND t.owner_id=?)""",
                           (data['name'], data['due_date'], data['notes'], subtask_id, task_id, owner_id))
        else:
            cursor.execute("UPDATE s SET name=?,due_date=?,notes=? FROM dbo.task_subtasks s JOIN dbo.tasks t ON t.id=s.task_id WHERE s.id=? AND s.task_id=? AND t.owner_id=?", (data['name'],data['due_date'],data['notes'],subtask_id,task_id,owner_id))
        if not cursor.rowcount: conn.close(); return None
    conn.commit(); conn.close(); return get_subtask(owner_id, task_id, subtask_id)


def delete_subtask(owner_id, task_id, subtask_id):
    subtask = get_subtask(owner_id, task_id, subtask_id)
    if not subtask: return None
    files = [item['stored_name'] for item in attachment_files(subtask_id)]
    conn = get_connection(); cursor = conn.cursor(); cursor.execute("DELETE FROM dbo.task_subtasks WHERE id=? AND task_id=?", (subtask_id, task_id)); conn.commit(); conn.close(); return files


def attachment_files(subtask_id):
    conn = get_connection(); cursor = conn.cursor(); cursor.execute("SELECT stored_name FROM dbo.task_subtask_attachments WHERE subtask_id=?", (subtask_id,)); result = _rows(cursor); conn.close(); return result
