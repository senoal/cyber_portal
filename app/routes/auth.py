import time

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, g
from werkzeug.security import check_password_hash
from app.models.user_model import get_user_by_username
from app.models.user_model import get_effective_menu_access
from app.services.access_control import landing_endpoint

auth_bp = Blueprint("auth", __name__)


# =========================
# LOGIN USER (UMUM)
# =========================
@auth_bp.route("/", methods=["GET", "POST"])
def login():
    if request.method == "GET" and request.args.get("document") and session.get("user_id"):
        return redirect(url_for("pentest_advisory.spa", document=request.args["document"]))
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        user = get_user_by_username(username)

        if user and check_password_hash(user["password"], password):
            # Discard any pre-login cookie state before establishing identity.
            # This also removes stale authorization fields from prior logins.
            session.clear()
            session.permanent = True
            session["last_activity_at"] = time.time()
            session["level"] = user["level"]
            session["user_id"] = user["id"]
            session["user"] = user["username"]
            session["role"] = user["role"]

            if user["role"] == "admin":
                g.log_category = "AUTH"
                g.log_action = "LOGIN_SUCCESS"
                g.log_detail = "Login succeeded; destination=admin_dashboard."
                return redirect(url_for("auth.admin_dashboard"))

            session["menu_access"] = list(get_effective_menu_access(user["id"], user["level"]))
            g.log_category = "AUTH"
            g.log_action = "LOGIN_SUCCESS"
            g.log_detail = f"Login succeeded; access_count={len(session['menu_access'])}."
            return redirect(url_for(landing_endpoint(session["menu_access"])))

        else:
            g.log_category = "AUTH"
            g.log_action = "LOGIN_FAILED"
            g.log_detail = "Authentication rejected: invalid username or password."
            flash("Username atau password salah!")

    return render_template("login.html")


# =========================
# LOGIN ADMIN
# =========================
@auth_bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        user = get_user_by_username(username)

        if user and check_password_hash(user["password"], password):
            session.clear()
            session.permanent = True
            session["last_activity_at"] = time.time()
            session["user"] = user["username"]
            session["role"] = user["role"]
            session["user_id"] = user["id"]   # ✅ TAMBAHKAN INI JUGA
            session["level"] = user["level"]
            session["menu_access"] = list(get_effective_menu_access(user["id"], user["level"]))

            if user["role"] == "admin":
                g.log_category = "AUTH"
                g.log_action = "ADMIN_LOGIN_SUCCESS"
                g.log_detail = "Administrator authentication succeeded."
                return redirect(url_for("auth.admin_dashboard"))
            else:
                g.log_category = "AUTH"
                g.log_action = "ADMIN_LOGIN_DENIED"
                g.log_detail = "Authentication succeeded but administrator role is required."
                flash("Akses ditolak! Anda bukan admin.")
                return redirect(url_for("auth.admin_login"))

        else:
            g.log_category = "AUTH"
            g.log_action = "ADMIN_LOGIN_FAILED"
            g.log_detail = "Authentication rejected: invalid username or password."
            flash("Username atau password salah!")

    return render_template("admin_login.html")


# =========================
# DASHBOARD ADMIN
# =========================
@auth_bp.route("/admin/dashboard")
def admin_dashboard():
    if session.get("role") != "admin":
        return redirect(url_for("auth.admin_login"))

    return render_template("admin_dashboard.html")


@auth_bp.route("/access-denied")
def access_denied():
    """Explain that an authenticated user has no explicit menu grant."""
    return render_template("access_denied.html"), 403


# =========================
# LOGOUT ADMIN
# =========================
@auth_bp.route("/admin/logout", methods=["POST"])
def admin_logout():
    g.log_category = "AUTH"
    g.log_action = "ADMIN_LOGOUT"
    g.log_detail = "Administrator signed out."
    session.clear()
    return redirect(url_for("auth.admin_login"))


# =========================
# LOGOUT USER
# =========================
@auth_bp.route("/logout", methods=["POST"])
def logout():
    g.log_category = "AUTH"
    g.log_action = "LOGOUT"
    g.log_detail = "User signed out."
    session.clear()
    return redirect(url_for("auth.login"))
