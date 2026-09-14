from app.database.db import get_connection, is_sqlite
from app.services.access_control import MENU_KEYS

_menu_access_table_ready = False
# Tasks is a core personal workspace.  Unlike optional security modules, it
# is always available to an authenticated portal user.
_ALWAYS_AVAILABLE_MENU_KEYS = {"tasks"}


def normalize_username(username):
    """Use one canonical representation everywhere credentials are compared."""
    return (username or "").strip()


def ensure_user_credential_columns():
    """Keep credential columns large enough for modern password hashes."""
    if is_sqlite():
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        DECLARE @username_length INT = (
            SELECT CHARACTER_MAXIMUM_LENGTH
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'users' AND COLUMN_NAME = 'username'
        );
        DECLARE @password_length INT = (
            SELECT CHARACTER_MAXIMUM_LENGTH
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'users' AND COLUMN_NAME = 'password'
        );
        IF @username_length IS NOT NULL AND @username_length < 150
            ALTER TABLE dbo.users ALTER COLUMN username NVARCHAR(150) NOT NULL;
        IF @password_length IS NOT NULL AND @password_length < 255
            ALTER TABLE dbo.users ALTER COLUMN password NVARCHAR(255) NOT NULL;
    """)
    conn.commit()
    conn.close()


def ensure_user_menu_access_table():
    """Create the small access-mapping table when the migration was not run yet."""
    global _menu_access_table_ready
    if _menu_access_table_ready:
        return
    if is_sqlite():
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_menu_access (
                user_id INTEGER NOT NULL,
                menu_key TEXT NOT NULL,
                PRIMARY KEY (user_id, menu_key),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        conn.commit()
        conn.close()
        _menu_access_table_ready = True
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        IF OBJECT_ID('dbo.user_menu_access', 'U') IS NULL
        CREATE TABLE dbo.user_menu_access (
            user_id INT NOT NULL,
            menu_key VARCHAR(50) NOT NULL,
            CONSTRAINT PK_user_menu_access PRIMARY KEY (user_id, menu_key),
            CONSTRAINT FK_user_menu_access_users FOREIGN KEY (user_id)
                REFERENCES dbo.users(id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    conn.close()
    _menu_access_table_ready = True


def get_explicit_menu_access(user_id):
    try:
        ensure_user_menu_access_table()
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT menu_key FROM dbo.user_menu_access WHERE user_id = ?", (user_id,))
        access = {row.menu_key for row in cursor.fetchall() if row.menu_key in MENU_KEYS}
        conn.close()
        return access
    except Exception:
        return set()


def get_effective_menu_access(user_id, level):
    return get_explicit_menu_access(user_id) | _ALWAYS_AVAILABLE_MENU_KEYS


def get_current_menu_access(user_id, level):
    """Return the latest configured access, or None when the database is unavailable."""
    try:
        ensure_user_menu_access_table()
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT menu_key FROM dbo.user_menu_access WHERE user_id = ?", (user_id,))
        explicit_access = {row.menu_key for row in cursor.fetchall() if row.menu_key in MENU_KEYS}
        conn.close()
        return explicit_access | _ALWAYS_AVAILABLE_MENU_KEYS
    except Exception:
        return None


def update_menu_access(user_id, menu_keys):
    selected = set(menu_keys) & MENU_KEYS
    ensure_user_menu_access_table()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM dbo.user_menu_access WHERE user_id = ?", (user_id,))
    for menu_key in selected:
        cursor.execute(
            "INSERT INTO dbo.user_menu_access (user_id, menu_key) VALUES (?, ?)",
            (user_id, menu_key),
        )
    conn.commit()
    conn.close()


# ======================
# GET ALL USERS
# ======================
def get_all_users():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT u.id, u.nama, u.username, u.password,
               s.Level, u.keterangan, u.role
        FROM users u
        LEFT JOIN service_access s ON u.service_access_id = s.id
    """)

    rows = cursor.fetchall()

    users = []
    for row in rows:
        users.append({
            "id": row.id,
            "nama": row.nama,
            "username": row.username,
            "password": row.password,
            "service_access": row.Level,
            "keterangan": row.keterangan,
            "role": row.role
        })

    conn.close()
    return users


# ======================
# GET USER BY USERNAME (LOGIN)
# ======================
# def get_user_by_username(username):
#     conn = get_connection()
#     cursor = conn.cursor()

#     cursor.execute("""
#         SELECT id, username, password, role
#         FROM users
#         WHERE username = ?
#     """, username)

#     row = cursor.fetchone()
#     conn.close()

#     if row:
#         return {
#             "id": row.id,
#             "username": row.username,
#             "password": row.password,
#             "role": row.role
#         }

#     return None
def get_user_by_username(username):
    username = normalize_username(username)
    if not username:
        return None
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            u.*,
            s.Level AS level
        FROM users u
        LEFT JOIN service_access s ON u.service_access_id = s.id
        WHERE LOWER(LTRIM(RTRIM(u.username))) = LOWER(?)
    """, (username,))

    row = cursor.fetchone()
    conn.close()

    if row:
        return dict(zip([column[0] for column in cursor.description], row))

    return None


# ======================
# ADD USER
# ======================
def add_user(data):
    ensure_user_credential_columns()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO users (nama, username, password, service_access_id, keterangan, role)
        OUTPUT INSERTED.id
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        data["nama"],
        data["username"],
        data["password"],
        data["service_access_id"],
        data["keterangan"],
        data["role"]
    )

    user_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return user_id


# ======================
# DELETE USER
# ======================
def delete_user(user_id):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # =========================
        # DELETE TASKS USER
        # =========================
        cursor.execute("""
            DELETE FROM pentest_tasks
            WHERE user_id = ?
        """, (user_id,))

        # =========================
        # DELETE USER
        # =========================
        cursor.execute("""
            DELETE FROM users
            WHERE id = ?
        """, (user_id,))

        conn.commit()

    except Exception as e:
        conn.rollback()
        raise e

    finally:
        conn.close()


# ======================
# GET SERVICE ACCESS (DROPDOWN)
# ======================
def get_services():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, Level FROM service_access")
    rows = cursor.fetchall()

    services = []
    for row in rows:
        services.append({
            "id": row.id,
            "nama": row.Level
        })

    conn.close()
    return services


def get_user_by_id(user_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT u.id, u.nama, u.username, u.password,
               s.Level, u.keterangan, u.role
        FROM users u
        LEFT JOIN service_access s ON u.service_access_id = s.id
        WHERE u.id = ?
    """, user_id)

    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            "id": row.id,
            "nama": row.nama,
            "username": row.username,
            "password": row.password,
            "service_access": row.Level,
            "keterangan": row.keterangan,
            "role": row.role
        }

    return None


def get_user_auth_state(user_id):
    """Return only the current server-side attributes used for authorization.

    Session cookies may identify a user, but role and service level must be
    sourced from the database on every authenticated request.  Keep this query
    deliberately narrow so credential hashes and profile fields are never read
    merely to authorize a request.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id, u.username, u.role, s.Level AS level
        FROM dbo.users AS u
        LEFT JOIN dbo.service_access AS s ON u.service_access_id = s.id
        WHERE u.id = ?
    """, user_id)
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None
    return {
        "id": row.id,
        "username": row.username,
        "role": row.role,
        "level": row.level,
    }


def username_exists(username, exclude_user_id=None):
    username = normalize_username(username)
    conn = get_connection()
    cursor = conn.cursor()
    query = """
        SELECT TOP 1 id FROM dbo.users
        WHERE LOWER(LTRIM(RTRIM(username))) = LOWER(?)
    """
    params = [username]
    if exclude_user_id is not None:
        query += " AND id <> ?"
        params.append(exclude_user_id)
    cursor.execute(query, params)
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

# def update_user_db(data):
#     conn = get_connection()
#     cursor = conn.cursor()

#     # =========================
#     # UPDATE DENGAN PASSWORD
#     # =========================
#     if data.get("password"):

#         cursor.execute("""
#             UPDATE users
#             SET 
#                 nama = ?,
#                 username = ?,
#                 password = ?,
#                 service_access_id = ?,
#                 keterangan = ?
#             WHERE id = ?
#         """,
#             data["nama"],
#             data["username"],
#             data["password"],
#             data["service_access_id"],
#             data["keterangan"],
#             data["user_id"]
#         )

#     # =========================
#     # UPDATE TANPA PASSWORD
#     # =========================
#     else:

#         cursor.execute("""
#             UPDATE users
#             SET 
#                 nama = ?,
#                 username = ?,
#                 service_access_id = ?,
#                 keterangan = ?
#             WHERE id = ?
#         """,
#             data["nama"],
#             data["username"],
#             data["service_access_id"],
#             data["keterangan"],
#             data["user_id"]
#         )

#     conn.commit()
#     conn.close()
def update_user_db(data):
    ensure_user_credential_columns()
    conn = get_connection()
    cursor = conn.cursor()

    # =========================
    # UPDATE DENGAN PASSWORD
    # =========================
    if "password" in data:

        cursor.execute("""
            UPDATE users
            SET
                nama = ?,
                username = ?,
                password = ?,
                service_access_id = ?,
                keterangan = ?
            WHERE id = ?
        """, (
            data["nama"],
            data["username"],
            data["password"],
            data["service_access_id"],
            data["keterangan"],
            data["user_id"]
        ))

    # =========================
    # UPDATE TANPA PASSWORD
    # =========================
    else:

        cursor.execute("""
            UPDATE users
            SET
                nama = ?,
                username = ?,
                service_access_id = ?,
                keterangan = ?
            WHERE id = ?
        """, (
            data["nama"],
            data["username"],
            data["service_access_id"],
            data["keterangan"],
            data["user_id"]
        ))

    conn.commit()
    conn.close()
