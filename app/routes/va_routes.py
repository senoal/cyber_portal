import os
import pandas as pd
import uuid
import re
from io import BytesIO
from datetime import datetime
from pathlib import Path
from flask import abort, send_file
from werkzeug.utils import secure_filename
from pypdf import PdfReader
from app.services.va_pdf_extractor import extract_va_fields

from app.models.va_model import (
    insert_va_bulk,
    get_latest_imported,
    create_va_record,
    get_attachment_by_id,
    get_attachment_by_va,
    delete_attachment_by_va,
    save_va_attachment,

    search_va,
    get_total_va,
    get_va_tracker_data,
    get_va_by_id,
    update_va_record,
    delete_va_record
)

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session
)



va_bp = Blueprint(
    "va",
    __name__,
    url_prefix="/user/va"
)


# =====================================================
# LOGIN CHECK
# =====================================================
def login_required():
    return "user" in session

# =====================================================
# GET VA UPLOAD PATH
# =====================================================
def get_va_upload_path():

    base_dir = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            ".."
        )
    )

    year = datetime.now().strftime("%Y")
    month = datetime.now().strftime("%m")

    absolute_folder = os.path.join(
        base_dir,
        "uploads",
        "va",
        year,
        month
    )

    relative_folder = os.path.join(
        "uploads",
        "va",
        year,
        month
    )

    os.makedirs(
        absolute_folder,
        exist_ok=True
    )

    return absolute_folder, relative_folder


def _legacy_extract_va_fields_from_pdf(pdf_file):
    """Extract summary data from Pentest Tools and Greenbone/OpenVAS VA reports."""
    reader = PdfReader(BytesIO(pdf_file.read()))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if not text.strip():
        raise ValueError("PDF tidak memiliki teks yang dapat dibaca. Gunakan PDF dengan teks, bukan hasil scan gambar.")

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    filename = (getattr(pdf_file, "filename", "") or "").lower()
    is_openvas = bool(re.search(r"Scan Rep ort|RESUL T O VER VIEW|Host Critical High Medium", text, re.I))
    profile = "Greenbone / OpenVAS" if is_openvas else "Website / Network Scanner"

    def next_value(label):
        for index, line in enumerate(lines[:-1]):
            if re.fullmatch(label, line, re.I):
                return lines[index + 1]
        return ""

    def parse_date(raw):
        raw = re.sub(r"\s*/\s*.*$", "", raw).strip()
        raw = re.sub(r"\b([A-Z])\s+([a-z]{1,2})\b", r"\1\2", raw)
        raw = re.sub(r"\b([A-Z][a-z])\s+([a-z])\b", r"\1\2", raw)
        raw = re.sub(r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+", "", raw)
        for pattern in ("%B %d, %Y", "%b %d, %Y", "%b %d %H:%M:%S %Y UTC", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(raw, pattern).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return ""

    if is_openvas:
        clean_text = re.sub(r"[\x00-\x1f]", " ", text)
        # OpenVAS identifies the scan target as "the task was <target>".
        # Keep this value as Asset; it can be a short web name, not only an IP.
        task_match = re.search(
            r"task\s+w\s+as\s+[^A-Za-z0-9]*([A-Za-z0-9][A-Za-z0-9._-]*)",
            clean_text,
            re.I,
        )
        asset = task_match.group(1).rstrip(".,") if task_match else ""
        # Some OpenVAS exports lose the first IP octets next to a control glyph
        # in "task was". Recover the complete host from the Results per Host title.
        if asset and re.fullmatch(r"[\d.]+", asset) and not re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", asset):
            host_match = re.search(r"2\.1\s+(\d{1,3}(?:\.\d{1,3}){3})\b", text)
            if host_match:
                asset = host_match.group(1)

        # Result Overview can contain IPs and FQDNs for the same target. Select
        # the FQDN that starts with the task value (e.g. aku.web -> aku.web.brinesia.app).
        source = ""
        if asset and not re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", asset):
            domain_match = re.search(
                rf"(?i)\b({re.escape(asset)}(?:\.[A-Za-z0-9-]+)+)\b",
                clean_text,
            )
            source = domain_match.group(1) if domain_match else asset
        else:
            source = asset

        summary_match = re.search(r"(?im)^\s*" + re.escape(source or asset) + r"\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+\d+\s+\d+", text) if (source or asset) else None
        # The per-service Threat Level table is more stable than the overview table
        # in exported OpenVAS PDFs, whose column spacing is often split by pypdf.
        service_section = re.search(
            r"Service\s*\(P\s*ort\)\s+Threat\s+Lev\s*el\s*(.*?)(?=\n\s*2\.1\.\d+\s+|\Z)",
            text,
            re.I | re.S,
        )
        threats = re.findall(
            r"(?im)^\s*(?:\d+/(?:tcp|udp)|general/[\w-]+)\s+(Critical|High|Medium|Lo\s*w)\s*$",
            service_section.group(1) if service_section else "",
        )
        if threats:
            normalized_threats = [re.sub(r"\s+", "", threat).lower() for threat in threats]
            critical = normalized_threats.count("critical")
            high = normalized_threats.count("high")
            medium = normalized_threats.count("medium")
            low = normalized_threats.count("low")
        else:
            critical, high, medium, low = (map(int, summary_match.groups()) if summary_match else (0, 0, 0, 0))
        info = 0
        date_match = re.search(r"scan started at\s+(.+?\s+\d{4}\s+UTC)", text, re.I)
        scan_date = parse_date(date_match.group(1)) if date_match else ""
    else:
        asset_match = re.search(r"(?m)^\s*(\d{1,3}(?:\.\d{1,3}){3})\s*$", "\n".join(lines[:30]))
        if asset_match:
            asset = asset_match.group(1)
            source = asset
        else:
            url_match = re.search(r"https?://[^\s)>,]+", text, re.I)
            source = url_match.group(0) if url_match else ""
            asset = re.sub(r"^https?://", "", source, flags=re.I).split("/")[0]
        critical = int(next_value("Critical:") or 0)
        high = int(next_value("High:") or 0)
        medium = int(next_value("Medium:") or 0)
        low = int(next_value("Low:") or 0)
        info = int(next_value("Info:") or 0)
        scan_date = parse_date(next_value("Start time:"))

    risk_level = next((level for level, count in (("Critical", critical), ("High", high), ("Medium", medium), ("Low", low), ("Info", info)) if count > 0), "Info")
    is_ip = bool(re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", asset or ""))
    is_web_target = "web" in f"{asset} {source}".lower()
    asset_type = "Web App" if is_web_target else ("Middleware" if "middleware" in filename else ("Server" if is_ip else "Web App"))
    return {"scan_date": scan_date, "source": source, "asset": asset, "asset_type": asset_type,
            "critical": critical, "high": high, "medium": medium, "low": low, "info": info,
            "risk_level": risk_level, "report_profile": profile}


def extract_va_fields_from_pdf(pdf_file):
    """Extract VA fields using the multi-profile PDF parser."""
    pdf_bytes = pdf_file.read()
    return extract_va_fields(pdf_bytes, getattr(pdf_file, "filename", ""))


# =====================================================
# VA DASHBOARD
# =====================================================
@va_bp.route("/", methods=["GET"])
def va_dashboard():

    if not login_required():
        return redirect(url_for("auth.login"))

    if session.get("level") != "Internal":
        return redirect(url_for("user.dashboard"))

    keyword = request.args.get("keyword", "").strip()
    status = request.args.get("status", "").strip()
    risk = request.args.get("risk", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    show_all = request.args.get("view") == "all"
    page = max(1, request.args.get("page", 1, type=int))
    per_page = 10
    total_records = get_total_va()

    # jika ada filter
    has_filters = (
        keyword
        or status
        or risk
        or date_from
        or date_to
    )

    if has_filters:

        latest_data = search_va(
            keyword=keyword,
            # status_kepentingan=status,
            risk_level=risk,
            date_from=date_from,
            date_to=date_to
        )

    elif show_all:
        total_pages = max(1, (total_records + per_page - 1) // per_page)
        page = min(page, total_pages)
        latest_data = search_va(page=page, per_page=per_page)

    else:

        latest_data = get_latest_imported()
        total_pages = 1

    return render_template(
        "internal/va.html",
        latest_data=latest_data,
        total_records=total_records,
        show_all=show_all,
        has_filters=has_filters,
        page=page,
        per_page=per_page,
        total_pages=total_pages if show_all and not has_filters else 1,
    )


# =====================================================
# VA COVERAGE TRACKER
# =====================================================
@va_bp.route("/tracker", methods=["GET"])
def va_tracker():
    """Show whether each registered asset has VA scan data in every month."""
    if not login_required():
        return redirect(url_for("auth.login"))

    if session.get("level") != "Internal":
        return redirect(url_for("user.dashboard"))

    tracker_data = get_va_tracker_data()
    available_years = sorted({row["year"] for row in tracker_data}, reverse=True)
    current_year = datetime.now().year
    selected_year = request.args.get("year", type=int)
    asset_filter = request.args.get("asset", "").strip()

    if selected_year not in available_years:
        selected_year = current_year if current_year in available_years else (available_years[0] if available_years else current_year)

    assets = {}
    for row in tracker_data:
        if row["year"] != selected_year:
            continue
        assets.setdefault(row["asset"], {})[row["month"]] = row

    tracker_rows = [
        {"asset": asset, "months": months, "completed_months": len(months)}
        for asset, months in sorted(assets.items(), key=lambda item: item[0].lower())
    ]

    if asset_filter:
        normalized_filter = asset_filter.casefold()
        tracker_rows = [
            row for row in tracker_rows
            if normalized_filter in row["asset"].casefold()
        ]

    total_completed = sum(row["completed_months"] for row in tracker_rows)
    total_expected = len(tracker_rows) * 12
    coverage_percent = round((total_completed / total_expected) * 100) if total_expected else 0
    per_page = 10
    total_assets = len(tracker_rows)
    total_pages = max(1, (total_assets + per_page - 1) // per_page)
    page = max(1, request.args.get("page", 1, type=int))
    page = min(page, total_pages)
    start_index = (page - 1) * per_page

    return render_template(
        "internal/va_tracker.html",
        tracker_rows=tracker_rows[start_index:start_index + per_page],
        available_years=available_years,
        selected_year=selected_year,
        total_completed=total_completed,
        total_expected=total_expected,
        coverage_percent=coverage_percent,
        total_assets=total_assets,
        page=page,
        total_pages=total_pages,
        asset_filter=asset_filter,
    )


# =====================================================
# IMPORT VA FILE
# =====================================================
@va_bp.route("/import", methods=["POST"])
def import_va():

    if not login_required():
        return redirect(url_for("auth.login"))

    if session.get("level") != "Internal":
        return redirect(url_for("user.dashboard"))

    file = request.files.get("file")

    if not file or file.filename == "":
        flash("Silakan pilih file terlebih dahulu.")
        return redirect(url_for("va.va_dashboard"))

    try:

        filename = secure_filename(file.filename)

        upload_folder = "uploads"

        os.makedirs(upload_folder, exist_ok=True)

        filepath = os.path.join(
            upload_folder,
            filename
        )

        file.save(filepath)

        ext = filename.split(".")[-1].lower()

        # ==========================
        # READ FILE
        # ==========================
        if ext == "csv":

            df = pd.read_csv(filepath)

        elif ext in ["xlsx", "xls"]:

            df = pd.read_excel(filepath)

        else:

            flash("Format file harus CSV atau Excel.")
            return redirect(url_for("va.va_dashboard"))

        # ==========================
        # NORMALIZE COLUMN
        # ==========================
        df.columns = (
            df.columns
            .astype(str)
            .str.strip()
        )

        # SUPPORT:
        # Status_Kepentingan_Asset
        # Status_Kepentingan_Aset

        # if "Status_Kepentingan_Asset" in df.columns:

        #     df.rename(
        #         columns={
        #             "Status_Kepentingan_Asset":
        #             "Status_Kepentingan_Aset"
        #         },
        #         inplace=True
        #     )

        # ==========================
        # VALIDATE COLUMN
        # ==========================
        required_columns = [
            "Scan_Date",
            "Source",
            "Asset",
            "Asset_Type",
            "Critical",
            "High",
            "Medium",
            "Low",
            "Info",
            "Risk_Level"
        ]

        missing_columns = [
            col
            for col in required_columns
            if col not in df.columns
        ]

        if missing_columns:

            flash(
                f"Kolom tidak ditemukan: {', '.join(missing_columns)}"
            )

            return redirect(
                url_for("va.va_dashboard")
            )

        # ==========================
        # CLEAN DATA
        # ==========================
        df = df.fillna(0)

        records = []

        for _, row in df.iterrows():

            records.append({

                "scan_date":
                    row["Scan_Date"],

                "source":
                    str(row["Source"]).strip(),

                "asset":
                    str(row["Asset"]).strip(),

                "asset_type":
                    str(row["Asset_Type"]).strip(),

                "critical":
                    int(row["Critical"]),

                "high":
                    int(row["High"]),

                "medium":
                    int(row["Medium"]),

                "low":
                    int(row["Low"]),

                "info":
                    int(row["Info"]),

                "risk_level":
                    str(row["Risk_Level"]).strip()

            })

        # ==========================
        # INSERT DB
        # ==========================
        insert_va_bulk(records)

        # ==========================
        # DELETE FILE
        # ==========================
        if os.path.exists(filepath):
            os.remove(filepath)

        flash(
            f"{len(records)} data berhasil diimport."
        )

    except Exception as e:

        flash(
            f"Gagal import data: {str(e)}"
        )

    return redirect(
        url_for("va.va_dashboard")
    )


# =====================================================
# CREATE MANUAL VA
# =====================================================
@va_bp.route("/extract-pdf", methods=["POST"])
def extract_va_pdf():
    if not login_required() or session.get("level") != "Internal":
        return {"success": False, "message": "Sesi tidak memiliki akses."}, 403

    pdf_file = request.files.get("pdf")
    if not pdf_file or not pdf_file.filename:
        return {"success": False, "message": "Pilih file PDF terlebih dahulu."}, 400
    if not pdf_file.filename.lower().endswith(".pdf"):
        return {"success": False, "message": "Hanya file PDF yang dapat diekstrak."}, 400
    if request.content_length and request.content_length > 10 * 1024 * 1024:
        return {"success": False, "message": "Ukuran PDF maksimal 10 MB."}, 400

    try:
        return {"success": True, "data": extract_va_fields_from_pdf(pdf_file)}
    except Exception as error:
        return {"success": False, "message": f"PDF tidak dapat diproses: {str(error)}"}, 400


@va_bp.route("/create", methods=["GET", "POST"])
def create_va():

    if not login_required():
        return redirect(url_for("auth.login"))

    if session.get("level") != "Internal":
        return redirect(url_for("user.dashboard"))

    if request.method == "POST":

        try:

            data = {

                "scan_date": request.form.get("scan_date"),
                "source": request.form.get("source"),
                "asset": request.form.get("asset"),
                "asset_type": request.form.get("asset_type"),
                "critical": request.form.get("critical", 0),
                "high": request.form.get("high", 0),
                "medium": request.form.get("medium", 0),
                "low": request.form.get("low", 0),
                "info": request.form.get("info", 0),
                "risk_level": request.form.get("risk_level")

            }

            # ==========================================
            # SIMPAN DATA VA
            # ==========================================
            va_id = create_va_record(data)

            # ==========================================
            # PROSES ATTACHMENT
            # ==========================================
            attachment = request.files.get("attachment")

            if attachment and attachment.filename:

                allowed_extensions = {
                    "pdf",
                    "doc",
                    "docx",
                    "xls",
                    "xlsx",
                    "csv",
                    "txt",
                    "png",
                    "jpg",
                    "jpeg",
                    "gif"
                }

                ext = attachment.filename.rsplit(".", 1)[1].lower()

                if ext not in allowed_extensions:

                    flash("Format file tidak didukung.")

                    return redirect(
                        url_for("va.create_va")
                    )

                # ==========================================
                # FOLDER
                # uploads/va/2026/07/
                # ==========================================
                absolute_folder, relative_folder = get_va_upload_path()

                # ==========================================
                # NAMA FILE BARU
                # ==========================================
                filename = (
                    f"VA_{uuid.uuid4().hex}.{ext}"
                )
                
                absolute_path = os.path.join(
                    absolute_folder,
                    filename
                )

                relative_path = os.path.join(
                    relative_folder,
                    filename
                )

                # ==========================================
                # SIMPAN FILE
                # ==========================================
                attachment.save(absolute_path)

                # ==========================================
                # SIMPAN METADATA
                # ==========================================
                save_va_attachment({

                    "va_id": va_id,

                    "file_name": filename,

                    "original_name":
                        attachment.filename,

                    "file_path":
                        relative_path,

                    "file_type":
                        ext,

                    "file_size":
                        os.path.getsize(absolute_path),

                    "uploaded_by":
                        session.get("user")

                })

            flash("Data VA berhasil disimpan.")

            return redirect(
                url_for("va.va_dashboard")
            )

        except Exception as e:

            flash(
                f"Gagal menyimpan data : {str(e)}"
            )

    return render_template(
        "internal/va_create.html"
    )
    
    
# =====================================================
# VIEW DETAIL VA
# =====================================================
@va_bp.route("/view/<int:va_id>")
def view_va(va_id):

    if not login_required():
        return redirect(url_for("auth.login"))

    if session.get("level") != "Internal":
        return redirect(url_for("user.dashboard"))

    data = get_va_by_id(va_id)
    attachment = get_attachment_by_va(va_id)

    if not data:

        flash("Data tidak ditemukan.")

        return redirect(
            url_for("va.va_dashboard")
        )

    return render_template(
        "internal/va_view.html",
        data=data,
        attachment=attachment
    )
    
    
# =====================================================
# Download VA
# =====================================================
def send_va_attachment(attachment):
    """Return a VA attachment as a download after validating its local path."""
    base_dir = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            ".."
        )
    )
    uploads_dir = os.path.abspath(os.path.join(base_dir, "uploads", "va"))
    file_path = os.path.abspath(
        os.path.join(base_dir, os.path.normpath(attachment.File_Path))
    )

    try:
        is_va_upload = os.path.commonpath([uploads_dir, file_path]) == uploads_dir
    except ValueError:
        is_va_upload = False

    # Older records can contain a stale File_Path after a file was moved.
    # Resolve those records safely from their generated file name instead.
    if not is_va_upload or not os.path.isfile(file_path):
        stored_name = os.path.basename(str(attachment.File_Name or ""))
        matching_files = (
            [path for path in Path(uploads_dir).rglob(stored_name) if path.is_file()]
            if stored_name else []
        )
        file_path = str(matching_files[0]) if matching_files else ""

    if not file_path or not os.path.isfile(file_path):
        abort(404, description="File attachment tidak ditemukan di server.")

    file_type = str(attachment.File_Type or "").lower()
    if file_type == "pdf":
        with open(file_path, "rb") as uploaded_file:
            if uploaded_file.read(5) != b"%PDF-":
                abort(422, description="Attachment PDF tidak valid atau rusak.")

    return send_file(
        file_path,
        as_attachment=True,
        download_name=attachment.File_Original_Name,
        mimetype="application/pdf" if file_type == "pdf" else None
    )


@va_bp.route("/download/<int:attachment_id>")
def download_attachment(attachment_id):

    if not login_required():
        return redirect(url_for("auth.login"))

    if session.get("level") != "Internal":
        return redirect(url_for("user.dashboard"))


    attachment = get_attachment_by_id(attachment_id)


    if not attachment:

        flash("Attachment tidak ditemukan.")

        return redirect(
            url_for("va.va_dashboard")
        )


    return send_va_attachment(attachment)


@va_bp.route("/<int:va_id>/attachment/download")
def download_va_attachment(va_id):
    """Download the current attachment for the VA record being viewed."""
    if not login_required():
        return redirect(url_for("auth.login"))

    if session.get("level") != "Internal":
        return redirect(url_for("user.dashboard"))

    attachment = get_attachment_by_va(va_id)

    if not attachment:
        flash("Data VA ini tidak memiliki attachment.")
        return redirect(url_for("va.view_va", va_id=va_id))

    return send_va_attachment(attachment)
    
# =====================================================
# EDIT VA
# =====================================================
@va_bp.route("/edit/<int:va_id>", methods=["GET", "POST"])
def edit_va(va_id):

    if not login_required():
        return redirect(url_for("auth.login"))

    if session.get("level") != "Internal":
        return redirect(url_for("user.dashboard"))

    data = get_va_by_id(va_id)

    if not data:
        flash("Data tidak ditemukan.")
        return redirect(url_for("va.va_dashboard"))

    attachment = get_attachment_by_va(va_id)

    if request.method == "POST":

        try:

            form_data = {

                "scan_date": request.form.get("scan_date"),
                "asset": request.form.get("asset"),
                "source": request.form.get("source"),
                "asset_type": request.form.get("asset_type"),
                "critical": request.form.get("critical", 0),
                "high": request.form.get("high", 0),
                "medium": request.form.get("medium", 0),
                "low": request.form.get("low", 0),
                "info": request.form.get("info", 0),
                "risk_level": request.form.get("risk_level")

            }

            # ==========================================
            # UPDATE DATA VA
            # ==========================================
            update_va_record(
                va_id,
                form_data
            )

            # ==========================================
            # CEK FILE BARU
            # ==========================================
            new_file = request.files.get("attachment")

            if new_file and new_file.filename != "":

                allowed = {
                    "pdf",
                    "doc",
                    "docx",
                    "xls",
                    "xlsx",
                    "csv",
                    "txt",
                    "png",
                    "jpg",
                    "jpeg",
                    "gif"
                }
                
                if "." not in new_file.filename:

                    flash("Nama file tidak valid.")

                    return redirect(
                        url_for("va.create_va")
                    )

                ext = new_file.filename.rsplit(".", 1)[1].lower()

                if ext not in allowed:

                    flash("Format file tidak didukung.")

                    return redirect(
                        url_for(
                            "va.edit_va",
                            va_id=va_id
                        )
                    )

                # ==========================================
                # HAPUS FILE LAMA
                # ==========================================
                old_attachment = get_attachment_by_va(va_id)

                if old_attachment:

                    base_dir = os.path.abspath(
                        os.path.join(
                            os.path.dirname(__file__),
                            "..",
                            ".."
                        )
                    )

                    old_path = os.path.join(
                        base_dir,
                        old_attachment.File_Path
                    )

                    old_path = os.path.normpath(old_path)

                    if os.path.exists(old_path):

                        os.remove(old_path)

                    # Remove the previous database record so the View page
                    # resolves the replacement file, not a deleted file.
                    delete_attachment_by_va(va_id)

                # ==========================================
                # BUAT FOLDER
                # ==========================================
                absolute_folder, relative_folder = get_va_upload_path()

                filename = f"VA_{uuid.uuid4().hex}.{ext}"

                absolute_path = os.path.join(
                    absolute_folder,
                    filename
                )

                relative_path = os.path.join(
                    relative_folder,
                    filename
                )

                new_file.save(absolute_path)

                # ==========================================
                # SIMPAN METADATA
                # ==========================================
                save_va_attachment({

                    "va_id": va_id,

                    "file_name": filename,

                    "original_name": new_file.filename,

                    "file_path": relative_path,

                    "file_type": ext,

                    "file_size": os.path.getsize(absolute_path),

                    "uploaded_by": session.get("user")

                })

            flash("Data berhasil diperbarui.")

            return redirect(
                url_for("va.va_dashboard")
            )

        except Exception as e:

            flash(f"Gagal update data : {str(e)}")

    attachment = get_attachment_by_va(va_id)

    return render_template(
        "internal/va_edit.html",
        data=data,
        attachment=attachment
    )
    
# =====================================================
# DELETE VA
# =====================================================
@va_bp.route("/delete/<int:va_id>", methods=["POST"])
def delete_va(va_id):

    if not login_required():
        return redirect(url_for("auth.login"))

    if session.get("level") != "Internal":
        return redirect(url_for("user.dashboard"))

    try:

        delete_va_record(va_id)

        flash("Data VA berhasil dihapus.")

    except Exception as e:

        flash(f"Gagal menghapus data: {str(e)}")

    return redirect(
        url_for("va.va_dashboard")
    )
