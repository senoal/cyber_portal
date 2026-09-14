import sqlite3
import time
from datetime import timedelta
from flask import Flask, current_app, flash, jsonify, redirect, request, session, url_for
from app.config import Config
from app.routes.auth import auth_bp
from app.routes.users import users_bp
from app.routes.user_routes import user_bp
from app.routes.va_routes import va_bp
from app.routes.pdf_routes import pdf_bp
from app.routes.application_directory_routes import application_directory_bp
from app.routes.tasks_routes import tasks_bp
from app.services.access_control import landing_endpoint, menu_for_endpoint
from app.services.audit_log import begin_request, write_response_audit
from app.services.csrf import csrf_token, validate_csrf_request
from app.models.user_model import get_current_menu_access, get_user_auth_state
from app.models.settings_model import get_session_idle_timeout_minutes


USER_PORTAL_ENDPOINT_PREFIXES = ("user.", "va.", "pdf_bp.", "application_directory.", "tasks.")


def is_user_portal_endpoint(endpoint):
    """Return whether an endpoint belongs to the non-admin workspace."""
    return bool(endpoint) and endpoint.startswith(USER_PORTAL_ENDPOINT_PREFIXES)


def create_app():
    Config.validate_security_configuration()
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static"
    )

    app.config.from_object(Config)

    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(va_bp)
    app.register_blueprint(pdf_bp)
    app.register_blueprint(application_directory_bp)
    app.register_blueprint(tasks_bp)

    @app.context_processor
    def inject_csrf_token():
        return {"csrf_token": csrf_token}

    @app.before_request
    def enforce_menu_access():
        begin_request()
        # Enforce idle expiry on the server as well as through the cookie's
        # expiry. Static assets do not extend a user's authenticated activity.
        if session.get("user_id") and request.endpoint != "static":
            now = time.time()
            last_activity = session.get("last_activity_at")
            timeout_minutes = get_session_idle_timeout_minutes()
            timeout = timeout_minutes * 60
            app.config["SESSION_IDLE_TIMEOUT_SECONDS"] = timeout
            app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(seconds=timeout)
            if not isinstance(last_activity, (int, float)) or now - last_activity >= timeout:
                was_admin = session.get("role") == "admin"
                session.clear()
                flash(
                    f"Sesi berakhir karena tidak ada aktivitas selama {timeout_minutes} menit.",
                    "warning",
                )
                return redirect(url_for("auth.admin_login" if was_admin else "auth.login"))
            session["last_activity_at"] = now
        validate_csrf_request()
        # ``role`` and ``level`` are convenience values in Flask's signed
        # cookie, not the source of authorization.  Rehydrate them from the
        # account record so a removed user or a revoked admin role loses access
        # immediately.  Login endpoints are excluded so a stale cookie cannot
        # prevent a new login attempt.
        if request.endpoint not in {"auth.login", "auth.admin_login", "static"}:
            user_id = session.get("user_id")
            if user_id:
                account = get_user_auth_state(user_id)
                if not account:
                    session.clear()
                    return redirect(url_for("auth.login"))
                session["user"] = account["username"]
                session["role"] = account["role"]
                session["level"] = account["level"]

        if session.get("role") == "admin":
            # Admin and user workspaces are intentionally separate.  Admin
            # sessions may manage accounts, but must not use user dashboards
            # or user-facing data routes through a guessed/direct URL.
            if is_user_portal_endpoint(request.endpoint):
                return redirect(url_for("auth.admin_dashboard"))
            return None

        # Access is refreshed from the administrator's configuration so a
        # revoked menu, including Tech, disappears immediately for active users.
        if session.get("user") and session.get("user_id"):
            current_access = get_current_menu_access(session["user_id"], session.get("level"))
            if current_access is not None:
                session["menu_access"] = sorted(current_access)

        menu_key = menu_for_endpoint(request.endpoint)
        if menu_key and session.get("user"):
            # Menu access is established at login and kept in the signed
            # session. Do not query SQL Server before every page request:
            # otherwise a temporary DB connection issue blocks every menu,
            # including static pages such as Tech.
            menu_access = set(session.get("menu_access", []))
            if menu_key not in menu_access:
                return redirect(url_for(landing_endpoint(menu_access)))
        return None

    @app.after_request
    def record_activity(response):
        write_response_audit(response)
        # A cached login form contains a CSRF token tied to an earlier signed
        # session. Mobile browsers are especially aggressive about restoring
        # such pages after app/server restarts, causing an avoidable 400.
        if request.endpoint in {"auth.login", "auth.admin_login"}:
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response

    @app.errorhandler(sqlite3.Error)
    def handle_database_connection_error(error):
        """Keep database outages from exposing a Flask traceback to users."""
        # JSON callers must never receive a redirect page: client-side Tasks
        # code expects an API response and can show this message to the user.
        if request.path.startswith("/api/"):
            current_app.logger.exception("SQLite API failure: %s", error)
            reason = str(error).lower()
            if "readonly" in reason:
                message = "Database SQLite bersifat read-only. Berikan izin Modify pada folder instance."
            elif "unable to open" in reason:
                message = "File database SQLite tidak dapat dibuka. Pastikan instance/sec_app.sqlite3 tersedia dan folder instance dapat ditulis."
            elif "locked" in reason or "busy" in reason:
                message = "Database SQLite sedang digunakan. Tunggu sebentar lalu coba simpan kembali."
            elif "no such table" in reason:
                message = "Struktur database Tasks belum tersedia. Deploy versi Tasks terbaru lalu restart aplikasi."
            else:
                message = "Task tidak dapat disimpan karena database SQLite lokal tidak tersedia."
            return jsonify(error=message), 500
        flash(
            "Layanan database sedang tidak tersedia. Silakan periksa database lokal atau koneksi SQL Server.",
            "error"
        )
        if session.get("user"):
            return redirect(url_for("user.dashboard"))
        return redirect(url_for("auth.login"))

    @app.errorhandler(400)
    def handle_bad_request(error):
        """Return JSON for invalid API requests, including invalid CSRF tokens."""
        if request.path.startswith("/api/"):
            return jsonify(error=getattr(error, "description", "Permintaan tidak valid.")), 400
        return error

    return app
