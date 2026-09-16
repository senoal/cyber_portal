import os
import secrets
from datetime import timedelta
from pathlib import Path


def _load_project_environment():
    """Load local deployment values without overriding a service environment.

    ``production.env`` is intentionally gitignored. It supports a portable
    copy-and-run deployment while allowing a Windows service environment or a
    secret manager to take precedence later.
    """
    env_path = Path(__file__).resolve().parent.parent / "production.env"
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("SEC_APP_"):
            os.environ.setdefault(key, value.strip())


_load_project_environment()


def _as_bool(value, default=False):
    return str(value if value is not None else default).strip().lower() in {"1", "true", "yes", "on"}


def _local_session_secret_path():
    """Keep a generated development/local-deployment secret out of static files."""
    # The project root is writable in local Windows deployments; unlike a
    # Flask instance folder it is not served by this application's static URL.
    return Path(__file__).resolve().parent.parent / ".sec_app_session_secret"


def _load_or_create_local_session_secret():
    """Return a persistent random secret when an environment secret is absent."""
    secret_path = _local_session_secret_path()
    try:
        existing_secret = secret_path.read_text(encoding="utf-8").strip()
        if len(existing_secret) >= 32:
            return existing_secret
    except FileNotFoundError:
        pass

    generated_secret = secrets.token_urlsafe(64)
    try:
        # O_EXCL prevents two simultaneous workers from overwriting each
        # other's session key during first startup.
        descriptor = os.open(str(secret_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as secret_file:
            secret_file.write(generated_secret)
        return generated_secret
    except FileExistsError:
        # Another worker created it first; use the shared persistent value.
        existing_secret = secret_path.read_text(encoding="utf-8").strip()
        if len(existing_secret) >= 32:
            return existing_secret
        raise RuntimeError("File secret sesi lokal tidak valid. Atur SEC_APP_SECRET_KEY.")


class Config:
    # Flask's default session is signed client-side data.  This value must
    # therefore be unique to the deployment and must never live in source
    # control.  A temporary key is acceptable only for local debug runs.
    SECRET_KEY = os.getenv("SEC_APP_SECRET_KEY")

    # Network settings can be changed on the server without editing source.
    # 0.0.0.0 listens on every network interface, including the LAN address.
    HOST = os.getenv("SEC_APP_HOST", "0.0.0.0")
    PORT = int(os.getenv("SEC_APP_PORT", "5000"))
    DEBUG = _as_bool(os.getenv("SEC_APP_DEBUG"), default=False)

    @classmethod
    def validate_security_configuration(cls):
        """Load a deployment secret or create a persistent local secret."""
        if cls.SECRET_KEY:
            return
        cls.SECRET_KEY = _load_or_create_local_session_secret()

    # Apply one consistent upload limit to every module.
    MAX_CONTENT_LENGTH = int(os.getenv("SEC_APP_MAX_UPLOAD_MB", "25")) * 1024 * 1024
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _as_bool(os.getenv("SEC_APP_HTTPS"), default=False)
    # A permanent session is refreshed only while requests continue arriving.
    SESSION_IDLE_TIMEOUT_SECONDS = 60
    PERMANENT_SESSION_LIFETIME = timedelta(seconds=SESSION_IDLE_TIMEOUT_SECONDS)
    SESSION_REFRESH_EACH_REQUEST = True

    # SQL Server is the primary backend. SQLite is used only when explicitly
    # requested for an offline rollback or local snapshot investigation.
    DATABASE_ENGINE = os.getenv("SEC_APP_DATABASE_ENGINE", "mssql").strip().lower()
    SQLITE_PATH = os.getenv(
        "SEC_APP_SQLITE_PATH", str(Path(__file__).resolve().parent.parent / "instance" / "sec_app.sqlite3")
    )
    MSSQL_SERVER = os.getenv("SEC_APP_DB_SERVER", "")
    MSSQL_DATABASE = os.getenv("SEC_APP_DB_DATABASE", "")
    MSSQL_UID = os.getenv("SEC_APP_DB_UID", "")
    MSSQL_PASSWORD = os.getenv("SEC_APP_DB_PASSWORD", "")
    MSSQL_PORT = int(os.getenv("SEC_APP_DB_PORT", "1433"))
