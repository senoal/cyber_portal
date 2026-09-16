"""Central, non-blocking audit logging for SEC_APP HTTP activity."""

import csv
import io
from datetime import date, datetime, timedelta
from time import perf_counter, monotonic

from flask import g, request, session

from app.database.db import get_connection, is_sqlite
from app.services.access_control import menu_for_endpoint

_table_ready = False
_database_retry_after = 0.0
_ignored_endpoints = {"static"}

_page_actions = {
    "auth.admin_dashboard": ("VIEW", "ADMIN_DASHBOARD_VIEWED", "Admin dashboard opened."),
    "users.manage_users": ("VIEW", "USER_MANAGEMENT_PAGE_VIEWED", "User management page opened."),
    "users.add_user": ("VIEW", "USER_CREATE_FORM_VIEWED", "Create-user form opened."),
    "users.view_user": ("VIEW", "USER_DETAILS_VIEWED", "User detail page opened."),
    "users.update_user": ("VIEW", "USER_EDIT_FORM_VIEWED", "User edit form opened."),
    "user.dashboard": ("MENU", "DASHBOARD_MENU_OPENED", "Dashboard menu opened."),
    "user.va_analysis": ("MENU", "VA_DASHBOARD_MENU_OPENED", "VA Dashboard menu opened."),
    "user.pentest": ("MENU", "PENTEST_MENU_OPENED", "Pentest menu opened."),
    "user.ip_intelligence": ("MENU", "IP_INTELLIGENCE_MENU_OPENED", "IP Intelligence menu opened."),
    "va.va_dashboard": ("MENU", "VA_REGISTER_MENU_OPENED", "VA Register menu opened."),
    "va.va_tracker": ("MENU", "VA_COVERAGE_TRACKER_OPENED", "VA Coverage Tracker menu opened."),
}


def ensure_audit_table():
    global _table_ready
    if _table_ready:
        return
    if is_sqlite():
        conn = get_connection()
        cursor = conn.cursor()
        # These tables are operational data for the admin area.  Keeping the
        # definitions here makes a restored/deployed SQLite snapshot complete
        # without silently disabling logging or exports.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                user_id INTEGER NULL,
                username TEXT NULL,
                user_role TEXT NULL,
                event_category TEXT NOT NULL,
                action_name TEXT NOT NULL,
                endpoint TEXT NULL,
                http_method TEXT NULL,
                request_path TEXT NULL,
                response_status INTEGER NULL,
                client_ip TEXT NULL,
                duration_ms INTEGER NULL,
                detail TEXT NULL
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS ix_activity_logs_created_at
            ON activity_logs(created_at DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS ix_activity_logs_user_id
            ON activity_logs(user_id, created_at DESC)
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_log_exports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                exported_by_user_id INTEGER NULL,
                exported_by_username TEXT NULL,
                range_start TEXT NOT NULL,
                range_end TEXT NOT NULL,
                record_count INTEGER NOT NULL,
                archive_purged INTEGER NOT NULL DEFAULT 0,
                filename TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()
        _table_ready = True
        return
    conn = get_connection()
    cursor = conn.cursor()
    # Normal runtime accounts need only read/write access. Do not submit a
    # batch containing CREATE TABLE on every process startup when the central
    # audit tables already exist, because SQL Server can require DDL rights
    # even though the IF branch is not taken.
    cursor.execute("""
        SELECT t.name
        FROM sys.tables t
        JOIN sys.schemas s ON s.schema_id = t.schema_id
        WHERE s.name = 'dbo' AND t.name IN ('activity_logs', 'activity_log_exports')
    """)
    if {row[0] for row in cursor.fetchall()} == {"activity_logs", "activity_log_exports"}:
        conn.close()
        _table_ready = True
        return
    cursor.execute("""
        IF OBJECT_ID('dbo.activity_logs', 'U') IS NULL
        BEGIN
            CREATE TABLE dbo.activity_logs (
                id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
                user_id INT NULL,
                username NVARCHAR(150) NULL,
                user_role NVARCHAR(50) NULL,
                event_category VARCHAR(20) NOT NULL,
                action_name VARCHAR(120) NOT NULL,
                endpoint VARCHAR(180) NULL,
                http_method VARCHAR(10) NULL,
                request_path NVARCHAR(500) NULL,
                response_status SMALLINT NULL,
                client_ip VARCHAR(64) NULL,
                duration_ms INT NULL,
                detail NVARCHAR(1000) NULL
            );
            CREATE INDEX IX_activity_logs_created_at ON dbo.activity_logs(created_at DESC);
            CREATE INDEX IX_activity_logs_user_id ON dbo.activity_logs(user_id, created_at DESC);
        END
        IF OBJECT_ID('dbo.activity_log_exports', 'U') IS NULL
        BEGIN
            CREATE TABLE dbo.activity_log_exports (
                id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                exported_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
                exported_by_user_id INT NULL,
                exported_by_username NVARCHAR(150) NULL,
                range_start DATE NOT NULL,
                range_end DATE NOT NULL,
                record_count INT NOT NULL,
                archive_purged BIT NOT NULL DEFAULT 0,
                filename NVARCHAR(255) NOT NULL
            );
        END
    """)
    conn.commit()
    conn.close()
    _table_ready = True


def _csv_buffer(rows):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow([
        "Log ID", "Waktu (UTC)", "Username", "Role", "Kategori", "Aktivitas",
        "Endpoint", "Metode", "Path", "Status", "IP Address", "Durasi (ms)", "Keterangan",
    ])
    for row in rows:
        values = list(row)
        if values[1]:
            values[1] = values[1].strftime("%Y-%m-%d %H:%M:%S")
        writer.writerow(values)
    return output.getvalue().encode("utf-8-sig")


def _export_rows(cursor, range_start, range_end):
    cursor.execute("""
        SELECT id, created_at, username, user_role, event_category, action_name,
               endpoint, http_method, request_path, response_status, client_ip,
               duration_ms, detail
        FROM dbo.activity_logs
        WHERE created_at >= ? AND created_at < ?
        ORDER BY id ASC
    """, (range_start, range_end))
    return cursor.fetchall()


def export_activity_csv(range_start, range_end):
    """Export an inclusive calendar-date range without modifying audit rows."""
    ensure_audit_table()
    conn = get_connection()
    cursor = conn.cursor()
    rows = _export_rows(cursor, range_start, range_end + timedelta(days=1))
    conn.close()
    return _csv_buffer(rows), len(rows)


def get_monthly_archive_candidates():
    """Completed calendar months that can be safely downloaded and purged."""
    ensure_audit_table()
    today = date.today()
    current_month_start = today.replace(day=1)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT CAST(DATEFROMPARTS(YEAR(created_at), MONTH(created_at), 1) AS DATE), COUNT(*)
        FROM dbo.activity_logs
        WHERE created_at < ?
        GROUP BY YEAR(created_at), MONTH(created_at)
        ORDER BY YEAR(created_at) DESC, MONTH(created_at) DESC
    """, (current_month_start,))
    candidates = [{"month_start": row[0], "record_count": row[1]} for row in cursor.fetchall()]
    conn.close()
    return candidates


def archive_month_to_csv(month_start, exported_by_user_id, exported_by_username):
    """Create a monthly CSV, retain export evidence, then purge that month's log rows."""
    if month_start.day != 1:
        raise ValueError("Arsip hanya dapat dibuat untuk satu bulan kalender penuh.")
    if month_start >= date.today().replace(day=1):
        raise ValueError("Bulan berjalan belum dapat diarsipkan.")
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    filename = f"SEC_APP_Audit_Log_{month_start:%Y_%m}.csv"
    ensure_audit_table()
    conn = get_connection()
    cursor = conn.cursor()
    try:
        rows = _export_rows(cursor, month_start, next_month)
        if not rows:
            raise ValueError("Tidak ada log untuk bulan yang dipilih.")
        csv_data = _csv_buffer(rows)
        cursor.execute("""
            INSERT INTO dbo.activity_log_exports
            (exported_by_user_id, exported_by_username, range_start, range_end,
             record_count, archive_purged, filename)
            VALUES (?, ?, ?, ?, ?, 1, ?)
        """, (exported_by_user_id, exported_by_username, month_start,
              next_month - timedelta(days=1), len(rows), filename))
        cursor.execute("DELETE FROM dbo.activity_logs WHERE created_at >= ? AND created_at < ?",
                       (month_start, next_month))
        conn.commit()
        return csv_data, filename, len(rows)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def begin_request():
    """Store request metadata before route handlers mutate the session."""
    g.audit_started = perf_counter()
    g.audit_actor = {
        "user_id": session.get("user_id"),
        "username": session.get("user"),
        "role": session.get("role"),
    }


def _event_metadata(response):
    endpoint = request.endpoint or "unknown"
    explicit_action = getattr(g, "log_action", None)
    if explicit_action:
        return (
            getattr(g, "log_category", "ACTION"),
            explicit_action[:120],
            getattr(g, "log_detail", None),
        )
    if endpoint in {"auth.login", "auth.admin_login"} and request.method == "POST":
        if session.get("user") and response.status_code < 400:
            return "AUTH", "LOGIN_SUCCESS", "Authentication completed successfully."
        return "AUTH", "LOGIN_FAILED", "Authentication was rejected."
    if endpoint in {"auth.logout", "auth.admin_logout"}:
        return "AUTH", "LOGOUT", "User signed out."
    if request.method == "GET" and endpoint in _page_actions:
        return _page_actions[endpoint]
    menu_key = menu_for_endpoint(endpoint)
    if request.method == "GET" and menu_key:
        return "MENU", "MENU_OPENED", f"menu={menu_key}"
    if request.method == "GET":
        return "VIEW", "PAGE_VIEWED", None
    action = endpoint.upper().replace(".", "_")
    return "ACTION", f"{action}_REQUESTED"[:120], None


def write_response_audit(response):
    """Record a completed request. Logging errors never affect the user request."""
    global _database_retry_after
    if (request.endpoint in _ignored_endpoints or request.path.startswith("/static/")
            or (request.endpoint == "users.activity_logs" and request.method == "GET")):
        return
    # Avoid repeatedly opening failed SQL connections for every page asset and
    # navigation while the database is temporarily unavailable.
    if monotonic() < _database_retry_after:
        return
    try:
        ensure_audit_table()
        category, action, detail = _event_metadata(response)
        actor = g.get("audit_actor", {})
        user_id = session.get("user_id") or actor.get("user_id")
        username = session.get("user") or actor.get("username")
        role = session.get("role") or actor.get("role")
        if not username and request.endpoint in {"auth.login", "auth.admin_login"}:
            username = request.form.get("username", "")[:150] or None
        duration = int((perf_counter() - g.get("audit_started", perf_counter())) * 1000)
        forwarded = request.headers.get("X-Forwarded-For", "")
        client_ip = (forwarded.split(",")[0].strip() if forwarded else request.remote_addr) or None
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO dbo.activity_logs
            (user_id, username, user_role, event_category, action_name, endpoint,
             http_method, request_path, response_status, client_ip, duration_ms, detail)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, username, role, category, action, request.endpoint,
              request.method, request.path[:500], response.status_code, client_ip,
              duration, detail))
        conn.commit()
        conn.close()
        _database_retry_after = 0.0
    except Exception:
        # Audit availability must not make core SEC_APP features unavailable.
        _database_retry_after = monotonic() + 60
        return


def get_activity_logs(page=1, per_page=25, username="", category=""):
    ensure_audit_table()
    conn = get_connection()
    cursor = conn.cursor()
    where, params = ["1=1"], []
    if username:
        where.append("username LIKE ?")
        params.append(f"%{username}%")
    if category:
        where.append("event_category = ?")
        params.append(category)
    condition = " AND ".join(where)
    cursor.execute(f"SELECT COUNT(*) FROM dbo.activity_logs WHERE {condition}", params)
    total = cursor.fetchone()[0]
    offset = (page - 1) * per_page
    cursor.execute(f"""
        SELECT id, created_at, username, user_role, event_category, action_name,
               endpoint, http_method, request_path, response_status, client_ip,
               duration_ms, detail
        FROM dbo.activity_logs WHERE {condition}
        ORDER BY id DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
    """, params + [offset, per_page])
    columns = [column[0] for column in cursor.description]
    logs = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return logs, total
