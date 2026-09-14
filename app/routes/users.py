import io
from datetime import date

from flask import Blueprint, render_template, request, redirect, url_for, session, g, send_file
from werkzeug.security import check_password_hash, generate_password_hash
from app.models.user_model import add_user as add_user_db, delete_user
from flask import flash
from math import ceil
from app.models.user_model import (
    get_all_users,
    add_user as add_user_db,
    delete_user as delete_user_db,
    get_services,
    get_user_by_id,
    update_user_db,
    get_effective_menu_access,
    update_menu_access,
    normalize_username,
    username_exists,
)
from app.services.access_control import MENU_KEYS, MENU_OPTIONS
from app.services.audit_log import (
    archive_month_to_csv,
    export_activity_csv,
    get_activity_logs,
    get_monthly_archive_candidates,
)
from app.models.settings_model import (
    get_session_idle_timeout_minutes,
    update_session_idle_timeout_minutes,
)

users_bp = Blueprint("users", __name__)


@users_bp.route("/admin/settings", methods=["GET", "POST"])
def settings():
    if session.get("role") != "admin":
        return redirect(url_for("auth.admin_login"))

    if request.method == "POST":
        try:
            minutes = update_session_idle_timeout_minutes(
                request.form.get("session_idle_timeout_minutes"), session.get("user_id")
            )
        except ValueError as error:
            flash(str(error), "error")
            return render_template(
                "settings.html",
                session_idle_timeout_minutes=request.form.get("session_idle_timeout_minutes", ""),
            ), 400
        except Exception:
            flash("Pengaturan belum dapat disimpan karena koneksi database tidak tersedia.", "error")
            return redirect(url_for("users.settings"))

        g.log_action = "SESSION_TIMEOUT_UPDATED"
        g.log_detail = f"session_idle_timeout_minutes={minutes}"
        flash("Durasi sesi berhasil diperbarui.", "success")
        return redirect(url_for("users.settings"))

    return render_template(
        "settings.html",
        session_idle_timeout_minutes=get_session_idle_timeout_minutes(),
    )

@users_bp.route("/admin/users")
def manage_users():
    if session.get("role") != "admin":
        return redirect(url_for("auth.admin_login"))

    users = get_all_users()
    for user in users:
        user["menu_access"] = get_effective_menu_access(user["id"], user["service_access"])
    g.log_action = "USER_MANAGEMENT_PAGE_VIEWED"
    g.log_category = "VIEW"
    g.log_detail = f"records_displayed={len(users)}"
    return render_template("users.html", users=users)


@users_bp.route("/admin/activity-logs")
def activity_logs():
    if session.get("role") != "admin":
        return redirect(url_for("auth.admin_login"))

    page = max(request.args.get("page", 1, type=int), 1)
    per_page = request.args.get("per_page", 50, type=int)
    if per_page not in {25, 50, 100}:
        per_page = 50
    username = request.args.get("username", "").strip()
    category = request.args.get("category", "").strip().upper()
    categories = ("AUTH", "MENU", "VIEW", "ACTION")
    if category not in categories:
        category = ""
    try:
        logs, total = get_activity_logs(
            page=page, per_page=per_page, username=username, category=category
        )
        archive_candidates = get_monthly_archive_candidates()
    except Exception:
        logs, total, archive_candidates = [], 0, []
        flash("Activity logs belum dapat dimuat karena koneksi database tidak tersedia.")
    total_pages = max(ceil(total / per_page), 1)
    if page > total_pages:
        page = total_pages
        try:
            logs, total = get_activity_logs(
                page=page, per_page=per_page, username=username, category=category
            )
        except Exception:
            logs, total = [], 0
    return render_template(
        "activity_logs.html", logs=logs, total=total, page=page,
        total_pages=total_pages, per_page=per_page, username=username,
        category=category, categories=categories, archive_candidates=archive_candidates,
    )


@users_bp.route("/admin/activity-logs/export")
def export_activity_logs():
    if session.get("role") != "admin":
        return redirect(url_for("auth.admin_login"))
    try:
        range_start = date.fromisoformat(request.args["date_from"])
        range_end = date.fromisoformat(request.args["date_to"])
        if range_start > range_end:
            raise ValueError
    except (KeyError, ValueError):
        flash("Pilih rentang tanggal log yang valid.")
        return redirect(url_for("users.activity_logs"))
    try:
        csv_data, record_count = export_activity_csv(range_start, range_end)
    except Exception:
        flash("CSV belum dapat dibuat karena koneksi database tidak tersedia.")
        return redirect(url_for("users.activity_logs"))
    filename = f"SEC_APP_Audit_Log_{range_start:%Y%m%d}_{range_end:%Y%m%d}.csv"
    g.log_action = "ACTIVITY_LOG_RANGE_EXPORTED"
    g.log_detail = f"range={range_start.isoformat()}..{range_end.isoformat()}; records={record_count}; filename={filename}"
    return send_file(io.BytesIO(csv_data), mimetype="text/csv", as_attachment=True, download_name=filename)


@users_bp.route("/admin/activity-logs/archive/<int:year>/<int:month>", methods=["POST"])
def archive_activity_log_month(year, month):
    if session.get("role") != "admin":
        return redirect(url_for("auth.admin_login"))
    try:
        month_start = date(year, month, 1)
        csv_data, filename, record_count = archive_month_to_csv(
            month_start, session.get("user_id"), session.get("user")
        )
    except (ValueError, IndexError):
        flash("Arsip bulanan tidak tersedia atau bukan bulan yang valid.")
        return redirect(url_for("users.activity_logs"))
    except Exception:
        flash("Arsip belum dapat dibuat karena koneksi database tidak tersedia.")
        return redirect(url_for("users.activity_logs"))
    g.log_action = "ACTIVITY_LOG_MONTH_ARCHIVED"
    g.log_detail = f"month={month_start:%Y-%m}; records_purged={record_count}; filename={filename}"
    return send_file(io.BytesIO(csv_data), mimetype="text/csv", as_attachment=True, download_name=filename)


@users_bp.route("/admin/users/add", methods=["GET", "POST"])
def add_user():
    if session.get("role") != "admin":
        return redirect(url_for("auth.admin_login"))

    services = get_services()

    if request.method == "POST":
        username = normalize_username(request.form["username"])
        menu_access = set(request.form.getlist("menu_access")) & MENU_KEYS
        if not menu_access:
            flash("Pilih minimal satu menu yang dapat diakses pengguna.")
            return render_template("user_form.html", services=services, menu_options=MENU_OPTIONS,
                                   menu_access=set()), 400
        if not username:
            flash("Username wajib diisi.")
            return redirect(url_for("users.add_user"))
        if username_exists(username):
            flash("Username sudah digunakan. Gunakan username lain.")
            return redirect(url_for("users.add_user"))
        data = {
            "nama": request.form["nama"],
            "username": username,
            "password": generate_password_hash(request.form["password"]),
            "service_access_id": request.form["service_access"],
            "keterangan": request.form["keterangan"],
            "role": "user"
        }

        try:
            user_id = add_user_db(data)
        except Exception:
            flash("User belum dapat disimpan. Periksa koneksi database atau jalankan migrasi kredensial.")
            return redirect(url_for("users.add_user"))
        update_menu_access(user_id, menu_access)

        g.log_action = "USER_CREATED"
        g.log_detail = (
            f"target_user_id={user_id}; target_username={data['username']}; "
            f"menu_access={','.join(sorted(menu_access))}"
        )

        flash("User berhasil ditambahkan!")
        return redirect(url_for("users.manage_users"))

    return render_template("user_form.html", services=services, menu_options=MENU_OPTIONS,
                           menu_access=set())

@users_bp.route("/admin/users/delete/<int:user_id>", methods=["POST"])
def delete_user(user_id):
    if session.get("role") != "admin":
        return redirect(url_for("auth.admin_login"))

    target_user = get_user_by_id(user_id)
    delete_user_db(user_id)  # ✅ FIX
    g.log_action = "USER_DELETED"
    g.log_detail = (
        f"target_user_id={user_id}; target_username="
        f"{target_user['username'] if target_user else 'unknown'}"
    )

    flash("User berhasil dihapus!")
    return redirect(url_for("users.manage_users"))


@users_bp.route("/admin/users/view/<int:user_id>")
def view_user(user_id):
    if session.get("role") != "admin":
        return redirect(url_for("auth.admin_login"))

    user = get_user_by_id(user_id)
    user["menu_access"] = get_effective_menu_access(user_id, user["service_access"])
    g.log_action = "USER_DETAILS_VIEWED"
    g.log_category = "VIEW"
    g.log_detail = f"target_user_id={user_id}; target_username={user['username']}"
    return render_template("user_view.html", user=user, menu_options=MENU_OPTIONS)

#     return render_template("user_form.html", user=user, services=services)
@users_bp.route("/admin/users/update/<int:user_id>", methods=["GET", "POST"])
def update_user(user_id):

    if session.get("role") != "admin":
        return redirect(url_for("auth.admin_login"))

    user = get_user_by_id(user_id)
    services = get_services()

    # =========================
    # UPDATE PROCESS
    # =========================
    if request.method == "POST":

        password = request.form.get("password", "")
        username = normalize_username(request.form["username"])
        if not username:
            flash("Username wajib diisi.")
            return render_template("user_form.html", user=user, services=services,
                                   menu_options=MENU_OPTIONS, menu_access=get_effective_menu_access(user_id, user["service_access"])), 400
        if username_exists(username, exclude_user_id=user_id):
            flash("Username sudah digunakan. Gunakan username lain.")
            return render_template("user_form.html", user=user, services=services,
                                   menu_options=MENU_OPTIONS, menu_access=get_effective_menu_access(user_id, user["service_access"])), 400

        data = {
            "nama": request.form["nama"],
            "username": username,
            "service_access_id": request.form["service_access"],
            "keterangan": request.form["keterangan"],
            "user_id": user_id
        }

        # =========================
        # UPDATE PASSWORD
        # =========================
        if password != "":
            data["password"] = generate_password_hash(password)

        menu_access = set(request.form.getlist("menu_access")) & MENU_KEYS
        if not menu_access:
            flash("Pilih minimal satu menu yang dapat diakses pengguna.")
            user["menu_access"] = get_effective_menu_access(user_id, user["service_access"])
            return render_template("user_form.html", user=user, services=services,
                                   menu_options=MENU_OPTIONS, menu_access=user["menu_access"]), 400
        try:
            update_user_db(data)
            update_menu_access(user_id, menu_access)
            updated_user = get_user_by_id(user_id)
            if not updated_user or normalize_username(updated_user["username"]) != username:
                raise RuntimeError("Username tidak tersimpan secara lengkap.")
            if password and not check_password_hash(updated_user["password"], password):
                raise RuntimeError("Hash password tidak dapat diverifikasi setelah disimpan.")
        except Exception:
            flash("Perubahan kredensial belum dapat disimpan dengan aman. Periksa migrasi database dan coba kembali.")
            return render_template("user_form.html", user=user, services=services,
                                   menu_options=MENU_OPTIONS, menu_access=menu_access), 500

        g.log_action = "USER_UPDATED"
        g.log_detail = (
            f"target_user_id={user_id}; previous_username={user['username']}; "
            f"new_username={data['username']}; menu_access={','.join(sorted(menu_access))}"
        )

        flash("User berhasil diupdate!")

        return redirect(url_for("users.manage_users"))

    # =========================
    # LOAD FORM
    # =========================
    g.log_action = "USER_EDIT_FORM_VIEWED"
    g.log_category = "VIEW"
    g.log_detail = f"target_user_id={user_id}; target_username={user['username']}"
    return render_template(
        "user_form.html",
        user=user,
        services=services,
        menu_options=MENU_OPTIONS,
        menu_access=get_effective_menu_access(user_id, user["service_access"])
    )
