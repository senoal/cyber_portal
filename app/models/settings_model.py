"""Persistent, application-wide settings controlled by administrators."""

from time import monotonic

from app.database.db import get_connection, is_sqlite

SESSION_IDLE_TIMEOUT_KEY = "session_idle_timeout_minutes"
DEFAULT_SESSION_IDLE_TIMEOUT_MINUTES = 1
_timeout_cache = {"value": DEFAULT_SESSION_IDLE_TIMEOUT_MINUTES, "until": 0.0}
_settings_table_ready = False


def ensure_settings_table():
    global _settings_table_ready
    if _settings_table_ready:
        return
    if is_sqlite():
        # A deployment can start with a valid SQLite database before the
        # optional settings row exists.  Create the storage idempotently so
        # the admin Settings page never depends on a separate manual step.
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                setting_key TEXT NOT NULL PRIMARY KEY,
                setting_value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_by_user_id INTEGER NULL
            )
        """)
        conn.commit()
        conn.close()
        _settings_table_ready = True
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        IF OBJECT_ID('dbo.app_settings', 'U') IS NULL
        BEGIN
            CREATE TABLE dbo.app_settings (
                setting_key VARCHAR(100) NOT NULL PRIMARY KEY,
                setting_value NVARCHAR(500) NOT NULL,
                updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
                updated_by_user_id INT NULL
            );
        END
    """)
    conn.commit()
    conn.close()
    _settings_table_ready = True


def get_session_idle_timeout_minutes():
    """Return a cached, valid timeout while keeping database outages non-fatal."""
    now = monotonic()
    if now < _timeout_cache["until"]:
        return _timeout_cache["value"]
    try:
        ensure_settings_table()
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT setting_value FROM dbo.app_settings WHERE setting_key = ?",
            (SESSION_IDLE_TIMEOUT_KEY,),
        )
        row = cursor.fetchone()
        conn.close()
        value = int(row.setting_value) if row else DEFAULT_SESSION_IDLE_TIMEOUT_MINUTES
        if value < 1:
            raise ValueError("Session timeout must be at least one minute.")
    except Exception:
        # Retain the last known policy during a brief database outage.
        value = _timeout_cache["value"]
    _timeout_cache.update(value=value, until=now + 15)
    return value


def update_session_idle_timeout_minutes(minutes, updated_by_user_id):
    try:
        minutes = int(minutes)
    except (TypeError, ValueError) as error:
        raise ValueError("Durasi sesi harus berupa angka bulat.") from error
    if minutes < 1:
        raise ValueError("Durasi sesi minimal 1 menit.")

    ensure_settings_table()
    conn = get_connection()
    cursor = conn.cursor()
    if is_sqlite():
        # The production snapshot may have been imported from SQL Server
        # without its original primary-key constraint.  Do not rely on SQLite
        # ON CONFLICT here: update an existing policy first, then insert it
        # when this is a fresh database.  This supports both old snapshots and
        # new SQLite deployments.
        cursor.execute("""
            UPDATE app_settings
            SET setting_value = ?, updated_at = CURRENT_TIMESTAMP,
                updated_by_user_id = ?
            WHERE setting_key = ?
        """, (str(minutes), updated_by_user_id, SESSION_IDLE_TIMEOUT_KEY))
        if cursor.rowcount == 0:
            cursor.execute("""
                INSERT INTO app_settings
                    (setting_key, setting_value, updated_at, updated_by_user_id)
                VALUES (?, ?, CURRENT_TIMESTAMP, ?)
            """, (SESSION_IDLE_TIMEOUT_KEY, str(minutes), updated_by_user_id))
    else:
        cursor.execute("""
        MERGE dbo.app_settings AS target
        USING (SELECT ? AS setting_key, ? AS setting_value, ? AS updated_by_user_id) AS source
        ON target.setting_key = source.setting_key
        WHEN MATCHED THEN UPDATE SET
            setting_value = source.setting_value,
            updated_at = SYSUTCDATETIME(),
            updated_by_user_id = source.updated_by_user_id
        WHEN NOT MATCHED THEN INSERT (setting_key, setting_value, updated_by_user_id)
            VALUES (source.setting_key, source.setting_value, source.updated_by_user_id);
    """, (SESSION_IDLE_TIMEOUT_KEY, str(minutes), updated_by_user_id))
    conn.commit()
    conn.close()
    _timeout_cache.update(value=minutes, until=monotonic() + 15)
    return minutes
