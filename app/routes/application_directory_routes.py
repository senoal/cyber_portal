import json
import os
from uuid import uuid4

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

from app.models.application_directory_model import delete_application, get_application, list_applications, save_application


application_directory_bp = Blueprint("application_directory", __name__, url_prefix="/user/applications")
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def _logged_in():
    return "user" in session


def _upload_images(modules):
    upload_dir = os.path.abspath(os.path.join("static", "uploads", "application_directory"))
    os.makedirs(upload_dir, exist_ok=True)
    saved = []
    for module_index, module in enumerate(modules):
        source_module_index = module.get("source_index", module_index)
        for step_index, step in enumerate(module["steps"]):
            source_step_index = step.get("source_index", step_index)
            step["images"] = list(step.get("existing_images", []))
            field_name = f"step_images_{source_module_index}_{source_step_index}"
            for image in request.files.getlist(field_name):
                if not image or not image.filename:
                    continue
                extension = os.path.splitext(secure_filename(image.filename))[1].lower()
                if extension not in _IMAGE_EXTENSIONS:
                    raise ValueError("Gambar langkah harus berformat PNG, JPG, GIF, atau WEBP.")
                filename = f"{uuid4().hex}{extension}"
                image.save(os.path.join(upload_dir, filename))
                saved.append(filename)
                step.setdefault("images", []).append(filename)
    return saved


def _clean_files(file_names):
    upload_dir = os.path.abspath(os.path.join("static", "uploads", "application_directory"))
    for file_name in file_names:
        path = os.path.join(upload_dir, os.path.basename(file_name))
        if os.path.isfile(path):
            os.remove(path)


def _form_data():
    try:
        modules = json.loads(request.form.get("modules_json", "[]"))
    except json.JSONDecodeError as error:
        raise ValueError("Struktur modul tidak valid.") from error
    if not request.form.get("name", "").strip():
        raise ValueError("Nama aplikasi wajib diisi.")
    cleaned_modules = []
    for module_index, module in enumerate(modules):
        module_name = str(module.get("name", "")).strip()
        cleaned_steps = []
        for step_index, step in enumerate(module.get("steps", [])):
            instruction = str(step.get("instruction", "")).strip()
            # Empty draft steps are intentionally ignored. They can be added
            # later from Edit without blocking creation of the application.
            if instruction:
                cleaned_steps.append({
                    "instruction": instruction,
                    "existing_images": step.get("existing_images", []),
                    "source_index": step_index,
                })
        # The client starts with an empty draft module. Do not persist it
        # until the user gives it a name.
        if not module_name:
            if cleaned_steps:
                raise ValueError("Isi nama modul sebelum menambahkan langkah.")
            continue
        cleaned_modules.append({"name": module_name, "steps": cleaned_steps, "source_index": module_index})
    return {"name": request.form["name"].strip(), "ip": request.form.get("ip", "").strip(), "purpose": request.form.get("purpose", "").strip(), "access_info": request.form.get("access_info", "").strip(), "modules": cleaned_modules}


@application_directory_bp.route("/")
def index():
    if not _logged_in(): return redirect(url_for("auth.login"))
    return render_template("user/application_directory.html", applications=list_applications())


@application_directory_bp.route("/add", methods=["GET", "POST"])
def add():
    if not _logged_in(): return redirect(url_for("auth.login"))
    if request.method == "POST":
        saved = []
        try:
            data = _form_data(); saved = _upload_images(data["modules"]); save_application(data)
            flash("Aplikasi berhasil ditambahkan.", "success")
            return redirect(url_for("application_directory.index"))
        except ValueError as error:
            _clean_files(saved); flash(str(error), "error")
    return render_template("user/application_directory_form.html", application=None)


@application_directory_bp.route("/<int:application_id>")
def view(application_id):
    if not _logged_in(): return redirect(url_for("auth.login"))
    application = get_application(application_id)
    if not application:
        flash("Data aplikasi tidak ditemukan.", "error"); return redirect(url_for("application_directory.index"))
    return render_template("user/application_directory_view.html", application=application)


@application_directory_bp.route("/<int:application_id>/edit", methods=["GET", "POST"])
def edit(application_id):
    if not _logged_in(): return redirect(url_for("auth.login"))
    application = get_application(application_id)
    if not application:
        flash("Data aplikasi tidak ditemukan.", "error"); return redirect(url_for("application_directory.index"))
    if request.method == "POST":
        saved = []
        try:
            data = _form_data(); saved = _upload_images(data["modules"]); _, old_images = save_application(data, application_id)
            retained = {image for module in data["modules"] for step in module["steps"] for image in step.get("images", [])}
            _clean_files([image for image in old_images if image not in retained]); flash("Data aplikasi berhasil diperbarui.", "success")
            return redirect(url_for("application_directory.view", application_id=application_id))
        except ValueError as error:
            _clean_files(saved); flash(str(error), "error")
    return render_template("user/application_directory_form.html", application=application)


@application_directory_bp.route("/<int:application_id>/delete", methods=["POST"])
def delete(application_id):
    if not _logged_in(): return redirect(url_for("auth.login"))
    _clean_files(delete_application(application_id))
    flash("Data aplikasi berhasil dihapus.", "success")
    return redirect(url_for("application_directory.index"))
