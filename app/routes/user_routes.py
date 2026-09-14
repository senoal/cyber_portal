import pandas as pd
import sqlite3
from app.models.pentest_model import get_all_pentest_with_user_paginated
from flask import Blueprint, render_template, session, redirect, url_for, request, send_file, jsonify
from app.models.pentest_model import get_all_pentest_with_user
from app.models.pentest_model import update_pentest_internal
from app.models.pentest_model import delete_pentest_by_id
from app.models.pentest_model import create_pentest, get_all_user_names
from app.models.pentest_model import search_pentest_internal
from app.models.pentest_model import (create_pentest_register, get_pentest_register, get_pentest_report,
    get_pentest_register_by_id, update_pentest_register, delete_pentest_register,
    get_pentest_tracker_items, create_pentest_tracker_item, update_pentest_tracker_item,
    delete_pentest_tracker_item, get_pentest_register_summary)
from app.models.pentest_model import get_all_user_names, get_all_users_for_dropdown
from app.services.ocr_engine import extract_text
from app.models.pentest_model import (
    create_pentest,
    get_pentest_by_user,
    get_pentest_by_id,
    update_pentest
)
from app.models.va_model import get_dashboard_summary
from app.models.va_model import get_dashboard_summary
from app.models.va_model import (
    get_dashboard_summary,
    get_risk_distribution,
    get_vulnerability_trend,
    get_vulnerability_by_asset_type,
    get_top5_asset_risk_score,
    get_top5_critical_vulnerability,
    get_vulnerability_severity_by_asset
)
from playwright.sync_api import sync_playwright
from werkzeug.utils import secure_filename
import os
import mimetypes
import json
import math
from html import escape
from PIL import Image
from io import BytesIO
from datetime import datetime
from uuid import uuid4
from app.models.ip_intelligence_model import get_all_ip
from flask import flash
from app.models.ip_intelligence_model import (get_all_ip, insert_ip, get_ip_summary, search_ip, get_ip_by_id, update_ip)
from app.services.pentest_tracker_report import build_pentest_tracker_report
from app.services.pentest_register_report import build_pentest_register_report
from app.services.pdf_html_converter import convert_pdf_to_html
from app.models.blackowl_org_model import get_organization, save_organization
from app.services.blackowl_org_report import build_blackowl_organization_pdf
import fitz


user_bp = Blueprint('user', __name__, url_prefix='/user')


def login_required():
    return 'user' in session


# ======================
# DASHBOARD
# ======================
@user_bp.route('/dashboard')
def dashboard():
    if not login_required():
        return redirect(url_for('auth.login'))
    return render_template('user/dashboard.html')


@user_bp.route('/va_analysis')
def va_analysis():

    if not login_required():
        return redirect(url_for('auth.login'))

    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    asset_type = request.args.get("asset_type")
    risk_level = request.args.get("risk_level")
    pdf_mode = request.args.get("pdf")

    db_error = None
    try:
        summary = get_dashboard_summary(
            date_from,
            date_to,
            asset_type,
            risk_level
        )
        risk_distribution = get_risk_distribution(date_from, date_to, asset_type, risk_level)
        trend_data = get_vulnerability_trend(date_from, date_to, asset_type, risk_level)
        asset_chart = get_vulnerability_by_asset_type(date_from, date_to, asset_type, risk_level)
        top5_risk_asset = get_top5_asset_risk_score(date_from, date_to, asset_type, risk_level)
        top5_critical_asset = get_top5_critical_vulnerability(date_from, date_to, asset_type, risk_level)
        severity_chart = get_vulnerability_severity_by_asset(date_from, date_to, asset_type, risk_level)
    except sqlite3.Error:
        # The dashboard remains accessible when SQL Server is unreachable. The
        # normal data flow resumes automatically as soon as the connection does.
        db_error = "Data VA belum dapat dimuat karena koneksi database tidak tersedia. Silakan coba lagi beberapa saat lagi."
        summary = {"total_asset": 0, "total_vulnerability": 0, "critical": 0, "high": 0, "medium": 0, "low": 0}
        risk_distribution = {"High": 0, "Medium": 0, "Low": 0, "High_Pct": 0, "Medium_Pct": 0, "Low_Pct": 0, "Total": 0}
        trend_data = []
        asset_chart = []
        top5_risk_asset = []
        top5_critical_asset = []
        severity_chart = []
    
    return render_template(
        'user/va_analysis.html',
        summary=summary,
        risk_distribution=risk_distribution,
        trend_data=trend_data,
        asset_chart=asset_chart,
        top5_risk_asset=top5_risk_asset,
        top5_critical_asset=top5_critical_asset,
        severity_chart=severity_chart,
        db_error=db_error,
        pdf_mode=pdf_mode,
    )
    


@user_bp.route('/vulnerability')
def vulnerability():
    if not login_required():
        return redirect(url_for('auth.login'))
    return render_template('user/vulnerability.html')


@user_bp.route('/tech')
def tech():
    """Technology workspace landing page (UI-only until feature flows are added)."""
    if not login_required():
        return redirect(url_for('auth.login'))
    return render_template('user/tech.html')


@user_bp.route('/tech/pdf-to-html')
def tech_pdf_to_html():
    if not login_required():
        return redirect(url_for('auth.login'))
    return render_template('user/tech_pdf_to_html.html')


@user_bp.route('/tech/pdf-to-html/convert', methods=['POST'])
def tech_pdf_to_html_convert():
    if not login_required():
        return redirect(url_for('auth.login'))
    pdf_file = request.files.get('pdf')
    if not pdf_file or not pdf_file.filename.lower().endswith('.pdf'):
        flash('Pilih file PDF yang valid.', 'error')
        return redirect(url_for('user.tech_pdf_to_html'))
    if request.content_length and request.content_length > 25 * 1024 * 1024:
        flash('Ukuran PDF maksimal 25 MB.', 'error')
        return redirect(url_for('user.tech_pdf_to_html'))

    document_id = uuid4().hex
    output_dir = os.path.abspath(os.path.join('uploads', 'tech_html', str(session.get('user_id', 'guest'))))
    os.makedirs(output_dir, exist_ok=True)
    source_path = os.path.join(output_dir, f'{document_id}.pdf')
    html_path = os.path.join(output_dir, f'{document_id}.html')
    pdf_file.save(source_path)
    try:
        convert_pdf_to_html(source_path, html_path, secure_filename(pdf_file.filename))
    except Exception as error:
        if os.path.isfile(source_path):
            os.remove(source_path)
        flash(f'PDF tidak dapat dikonversi: {error}', 'error')
        return redirect(url_for('user.tech_pdf_to_html'))

    session['tech_html_document'] = document_id
    return render_template('user/tech_pdf_to_html.html', document_id=document_id,
                           original_name=secure_filename(pdf_file.filename))


@user_bp.route('/tech/pdf-to-html/<document_id>/view')
def tech_pdf_to_html_view(document_id):
    if not login_required():
        return redirect(url_for('auth.login'))
    if document_id != session.get('tech_html_document'):
        return 'Dokumen tidak ditemukan.', 404
    html_path = os.path.abspath(os.path.join('uploads', 'tech_html', str(session.get('user_id', 'guest')), f'{document_id}.html'))
    if not os.path.isfile(html_path):
        return 'Dokumen tidak ditemukan.', 404
    return send_file(html_path, mimetype='text/html; charset=utf-8', as_attachment=False)


def _valid_pdf_uploads(files, minimum=1):
    uploads = [file for file in files if file and file.filename]
    if len(uploads) < minimum:
        raise ValueError('Pilih file PDF yang valid.')
    if any(not file.filename.lower().endswith('.pdf') for file in uploads):
        raise ValueError('Semua file harus berformat PDF.')
    sizes = []
    for file in uploads:
        position = file.stream.tell()
        file.stream.seek(0, os.SEEK_END)
        sizes.append(file.stream.tell())
        file.stream.seek(position)
    if sum(sizes) > 50 * 1024 * 1024:
        raise ValueError('Total ukuran file maksimal 50 MB.')
    return uploads


def _merge_pdf_uploads(files):
    """Create a merged document from uploaded PDF streams."""
    merged = fitz.open()
    try:
        for file in files:
            source = fitz.open(stream=file.read(), filetype='pdf')
            merged.insert_pdf(source)
            source.close()
        return merged
    except Exception:
        merged.close()
        raise


@user_bp.route('/tech/merge-pdf/preview', methods=['POST'])
def tech_merge_pdf_preview():
    """Render the selected output page so image placement needs no CDN viewer."""
    if not login_required():
        return jsonify(error='Sesi Anda telah berakhir.'), 401
    try:
        files = _valid_pdf_uploads(request.files.getlist('pdfs'), minimum=2)
        page_number = int(request.form.get('page', '1'))
        merged = _merge_pdf_uploads(files)
        if page_number < 1 or page_number > len(merged):
            raise ValueError(f'Halaman harus berada antara 1 dan {len(merged)}.')
        page = merged[page_number - 1]
        # A restrained resolution keeps the preview quick while coordinates remain PDF-native.
        pixmap = page.get_pixmap(matrix=fitz.Matrix(1.25, 1.25), alpha=False)
        response = send_file(BytesIO(pixmap.tobytes('png')), mimetype='image/png')
        response.headers['X-Pdf-Page-Count'] = str(len(merged))
        response.headers['X-Pdf-Page-Width'] = str(page.rect.width)
        response.headers['X-Pdf-Page-Height'] = str(page.rect.height)
        merged.close()
        return response
    except (ValueError, fitz.FileDataError, RuntimeError) as error:
        return jsonify(error=f'Pratinjau PDF tidak dapat dibuat: {error}'), 400


def _insert_pdf_image(document, image_file, raw_position):
    """Validate and permanently place the image using PDF-point coordinates."""
    if not image_file or not image_file.filename:
        return
    image_bytes = image_file.read()
    if not image_bytes or len(image_bytes) > 10 * 1024 * 1024:
        raise ValueError('Gambar tidak valid atau melebihi 10 MB.')
    try:
        position = json.loads(raw_position or '')
        page_index = int(position['page']) - 1
        x, y, width, height = (float(position[key]) for key in ('x', 'y', 'width', 'height'))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise ValueError('Posisi gambar tidak valid.')
    if page_index < 0 or page_index >= len(document) or width <= 0 or height <= 0:
        raise ValueError('Posisi gambar tidak valid.')
    page = document[page_index]
    rect = fitz.Rect(x, y, x + width, y + height) & page.rect
    if rect.is_empty or rect.width < 1 or rect.height < 1:
        raise ValueError('Gambar harus berada di dalam halaman PDF.')
    page.insert_image(rect, stream=image_bytes, keep_proportion=False, overlay=True)


def _watermark_options(raw_options):
    try:
        options = json.loads(raw_options or '{}')
        scale = float(options.get('scale', 42))
        rotation = float(options.get('rotation', 45))
        thickness = float(options.get('thickness', 2))
    except (ValueError, TypeError, json.JSONDecodeError):
        raise ValueError('Pengaturan watermark tidak valid.')
    if not 10 <= scale <= 80 or not -180 <= rotation <= 180 or not .1 <= thickness <= 10:
        raise ValueError('Nilai pengaturan watermark berada di luar batas.')
    return scale, rotation, thickness


def _apply_pdf_watermark(document, watermark_type, watermark_text, watermark_image, raw_options=None):
    """Apply one subtle watermark consistently to every page."""
    if not watermark_type:
        return
    scale, rotation, thickness = _watermark_options(raw_options)
    if watermark_type == 'text':
        text = (watermark_text or '').strip()
        if not text or len(text) > 80:
            raise ValueError('Teks watermark harus berisi 1 sampai 80 karakter.')
        # SVG is a single vector object, avoiding repeated-glyph artifacts
        # observed with transformed PDF text in some viewer engines.
        font_size = max(34, min(130, 900 / max(len(text), 1)))
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="1000">
          <text x="500" y="525" text-anchor="middle" font-family="Helvetica, Arial, sans-serif"
            font-size="{font_size}" font-weight="700" fill="#596b80" fill-opacity="0.22"
            stroke="#596b80" stroke-opacity="0.22" stroke-width="{max(.2, .2 + (thickness - 1) * 3)}"
            transform="rotate({-rotation} 500 500)">{escape(text)}</text></svg>'''.encode('utf-8')
        svg_document = fitz.open(stream=svg, filetype='svg')
        # Rasterize the single SVG object once at high resolution. Embedding
        # the SVG as a nested PDF form can be repeated by some viewer engines.
        watermark_bytes = svg_document[0].get_pixmap(
            matrix=fitz.Matrix(4, 4), alpha=True
        ).tobytes('png')
        svg_document.close()
        for page in document:
            width = page.rect.width * scale / 100
            height = width
            rect = fitz.Rect((page.rect.width - width) / 2, (page.rect.height - height) / 2,
                             (page.rect.width + width) / 2, (page.rect.height + height) / 2)
            page.insert_image(rect, stream=watermark_bytes, keep_proportion=True, overlay=True)
    elif watermark_type == 'image':
        if not watermark_image or not watermark_image.filename:
            raise ValueError('Pilih gambar untuk watermark.')
        image_bytes = watermark_image.read()
        if not image_bytes or len(image_bytes) > 10 * 1024 * 1024:
            raise ValueError('Gambar watermark tidak valid atau melebihi 10 MB.')
        try:
            image = Image.open(BytesIO(image_bytes)).convert('RGBA')
            image = image.rotate(-rotation, expand=True, resample=Image.Resampling.BICUBIC)
            alpha = image.getchannel('A').point(lambda value: int(value * min(1, thickness / 4)))
            image.putalpha(alpha)
            image_output = BytesIO()
            image.save(image_output, format='PNG')
            image_bytes = image_output.getvalue()
        except (OSError, ValueError) as error:
            raise ValueError(f'Gambar watermark tidak dapat diproses: {error}')
        for page in document:
            width, height = page.rect.width * scale / 100, page.rect.height * scale / 100
            rect = fitz.Rect((page.rect.width - width) / 2, (page.rect.height - height) / 2,
                             (page.rect.width + width) / 2, (page.rect.height + height) / 2)
            page.insert_image(rect, stream=image_bytes, keep_proportion=True, overlay=True)
    else:
        raise ValueError('Jenis watermark tidak valid.')


def _apply_pen_strokes(document, raw_strokes):
    if not raw_strokes:
        return
    try:
        strokes = json.loads(raw_strokes)
    except json.JSONDecodeError:
        raise ValueError('Data e-sign pen tidak valid.')
    if not isinstance(strokes, list) or len(strokes) > 100:
        raise ValueError('Jumlah goresan e-sign tidak valid.')
    for stroke in strokes:
        points = stroke.get('points', []) if isinstance(stroke, dict) else []
        page_index = int(stroke.get('page', 0)) - 1 if isinstance(stroke, dict) else -1
        width = float(stroke.get('width', 2)) if isinstance(stroke, dict) else 2
        color = stroke.get('color', '#173f67') if isinstance(stroke, dict) else '#173f67'
        if page_index < 0 or page_index >= len(document) or len(points) > 3000 or width < .5 or width > 12:
            raise ValueError('Data goresan e-sign tidak valid.')
        # A quick tap can create a single-point stroke. It has no visible line,
        # so it should not prevent the rest of the signature from being saved.
        if len(points) < 2:
            continue
        if not isinstance(color, str) or not color.startswith('#') or len(color) != 7:
            raise ValueError('Warna e-sign tidak valid.')
        rgb = tuple(int(color[index:index + 2], 16) / 255 for index in (1, 3, 5))
        page = document[page_index]
        shape = page.new_shape()
        previous = None
        for point in points:
            x, y = float(point['x']), float(point['y'])
            if not math.isfinite(x) or not math.isfinite(y):
                raise ValueError('Koordinat goresan e-sign tidak valid.')
            # Browser previews can differ by a fraction of a point after zooming.
            # Clamp those rounding differences to the page instead of rejecting
            # an otherwise valid signature with a 400 response.
            current = fitz.Point(
                min(max(x, page.rect.x0), page.rect.x1),
                min(max(y, page.rect.y0), page.rect.y1),
            )
            if previous:
                shape.draw_line(previous, current)
            previous = current
        shape.finish(color=rgb, width=width, stroke_opacity=.95)
        shape.commit(overlay=True)


@user_bp.route('/tech/edit-pdf', methods=['GET', 'POST'])
def tech_edit_pdf():
    if not login_required():
        return redirect(url_for('auth.login'))
    if request.method == 'GET':
        return render_template('user/tech_edit_pdf.html')
    try:
        file = _valid_pdf_uploads([request.files.get('pdf')], minimum=1)[0]
        document = fitz.open(stream=file.read(), filetype='pdf')
        _insert_pdf_image(document, request.files.get('overlay_image'), request.form.get('image_position'))
        _apply_pen_strokes(document, request.form.get('pen_strokes'))
        result = BytesIO(document.tobytes(garbage=4, deflate=True))
        document.close()
    except (ValueError, fitz.FileDataError, RuntimeError) as error:
        if request.headers.get('X-Edit-Pdf-Request') == '1':
            return jsonify(error=f'PDF tidak dapat diproses: {error}'), 400
        flash(f'PDF tidak dapat diedit: {error}', 'error')
        return redirect(url_for('user.tech_edit_pdf'))
    return send_file(result, mimetype='application/pdf', as_attachment=True, download_name='edited.pdf')


@user_bp.route('/tech/watermark-pdf', methods=['GET', 'POST'])
def tech_watermark_pdf():
    if not login_required():
        return redirect(url_for('auth.login'))
    flash('Modul Watermark PDF sedang dinonaktifkan sementara.', 'error')
    return redirect(url_for('user.tech'))


@user_bp.route('/tech/watermark-pdf/preview', methods=['POST'])
def tech_watermark_pdf_preview():
    if not login_required():
        return jsonify(error='Sesi Anda telah berakhir.'), 401
    return jsonify(error='Modul Watermark PDF sedang dinonaktifkan sementara.'), 503
    try:
        file = _valid_pdf_uploads([request.files.get('pdf')], minimum=1)[0]
        document = fitz.open(stream=file.read(), filetype='pdf')
        page_number = int(request.form.get('page', '1'))
        watermark_type = request.form.get('watermark_type')
        if watermark_type:
            _apply_pdf_watermark(document, watermark_type, request.form.get('watermark_text'),
                                 request.files.get('watermark_image'), request.form.get('watermark_options'))
        if page_number < 1 or page_number > len(document):
            raise ValueError(f'Halaman harus berada antara 1 dan {len(document)}.')
        page = document[page_number - 1]
        pixmap = page.get_pixmap(matrix=fitz.Matrix(1.25, 1.25), alpha=False)
        response = send_file(BytesIO(pixmap.tobytes('png')), mimetype='image/png')
        response.headers['X-Pdf-Page-Count'] = str(len(document))
        response.headers['X-Pdf-Page-Width'] = str(page.rect.width)
        response.headers['X-Pdf-Page-Height'] = str(page.rect.height)
        document.close()
        return response
    except (ValueError, fitz.FileDataError, RuntimeError) as error:
        return jsonify(error=f'Pratinjau PDF tidak dapat dibuat: {error}'), 400


@user_bp.route('/tech/edit-pdf/preview', methods=['POST'])
def tech_edit_pdf_preview():
    if not login_required():
        return jsonify(error='Sesi Anda telah berakhir.'), 401
    try:
        file = _valid_pdf_uploads([request.files.get('pdf')], minimum=1)[0]
        document = fitz.open(stream=file.read(), filetype='pdf')
        page_number = int(request.form.get('page', '1'))
        if page_number < 1 or page_number > len(document):
            raise ValueError(f'Halaman harus berada antara 1 dan {len(document)}.')
        page = document[page_number - 1]
        pixmap = page.get_pixmap(matrix=fitz.Matrix(1.25, 1.25), alpha=False)
        response = send_file(BytesIO(pixmap.tobytes('png')), mimetype='image/png')
        response.headers['X-Pdf-Page-Count'] = str(len(document))
        response.headers['X-Pdf-Page-Width'] = str(page.rect.width)
        response.headers['X-Pdf-Page-Height'] = str(page.rect.height)
        document.close()
        return response
    except (ValueError, fitz.FileDataError, RuntimeError) as error:
        return jsonify(error=f'Pratinjau PDF tidak dapat dibuat: {error}'), 400


@user_bp.route('/tech/merge-pdf', methods=['GET', 'POST'])
def tech_merge_pdf():
    if not login_required():
        return redirect(url_for('auth.login'))
    if request.method == 'GET':
        return render_template('user/tech_merge_pdf.html')
    try:
        files = _valid_pdf_uploads(request.files.getlist('pdfs'), minimum=2)
        merged = _merge_pdf_uploads(files)
        result = BytesIO(merged.tobytes(garbage=4, deflate=True))
        merged.close()
    except (ValueError, fitz.FileDataError, RuntimeError) as error:
        flash(f'PDF tidak dapat digabung: {error}', 'error')
        return redirect(url_for('user.tech_merge_pdf'))
    return send_file(result, mimetype='application/pdf', as_attachment=True, download_name='merged.pdf')


def _pages_to_delete(raw_pages, total_pages):
    pages = set()
    for part in raw_pages.replace(' ', '').split(','):
        if not part:
            continue
        try:
            start, end = (part.split('-', 1) + [part])[:2] if '-' in part else (part, part)
            start, end = int(start), int(end)
        except ValueError:
            raise ValueError('Format halaman tidak valid. Gunakan contoh: 1, 3-5.')
        if start < 1 or end < start or end > total_pages:
            raise ValueError(f'Nomor halaman harus berada antara 1 dan {total_pages}.')
        pages.update(range(start - 1, end))
    if not pages:
        raise ValueError('Masukkan halaman yang ingin dihapus.')
    if len(pages) == total_pages:
        raise ValueError('Setidaknya satu halaman harus tetap dipertahankan.')
    return sorted(pages, reverse=True)


@user_bp.route('/tech/delete-pdf', methods=['GET', 'POST'])
def tech_delete_pdf():
    if not login_required():
        return redirect(url_for('auth.login'))
    if request.method == 'GET':
        return render_template('user/tech_delete_pdf.html')
    try:
        pdf_file = _valid_pdf_uploads([request.files.get('pdf')])[0]
        pdf_file.stream.seek(0, os.SEEK_END)
        file_size = pdf_file.stream.tell()
        pdf_file.stream.seek(0)
        if file_size > 25 * 1024 * 1024:
            raise ValueError('Ukuran PDF maksimal 25 MB.')
        document = fitz.open(stream=pdf_file.read(), filetype='pdf')
        for page_number in _pages_to_delete(request.form.get('pages', ''), document.page_count):
            document.delete_page(page_number)
        result = BytesIO(document.tobytes(garbage=4, deflate=True))
        document.close()
    except (ValueError, fitz.FileDataError, RuntimeError) as error:
        flash(f'PDF tidak dapat diproses: {error}', 'error')
        return redirect(url_for('user.tech_delete_pdf'))
    return send_file(result, mimetype='application/pdf', as_attachment=True, download_name='pages_removed.pdf')


@user_bp.route('/profile-blackowl')
def profile_blackowl():
    """BlackOwl IT Security Department organization profile."""
    if not login_required():
        return redirect(url_for('auth.login'))
    try:
        organization = get_organization()
    except sqlite3.Error:
        organization = None
    return render_template('user/profile_blackowl.html', organization=organization)


@user_bp.route('/profile-blackowl/structure', methods=['POST'])
def save_profile_blackowl_structure():
    if not login_required():
        return jsonify({"error": "Silakan login kembali."}), 401
    structure = request.get_json(silent=True)
    if not isinstance(structure, dict) or not isinstance(structure.get('teams'), list):
        return jsonify({"error": "Struktur organisasi tidak valid."}), 400
    head_name = structure.get('head', {}).get('name', '') if isinstance(structure.get('head'), dict) else structure.get('head', '')
    if not isinstance(head_name, str) or len(head_name) > 80 or len(structure['teams']) > 20:
        return jsonify({"error": "Struktur organisasi melebihi batas yang diizinkan."}), 400
    try:
        save_organization(structure, session.get('user_id'))
    except sqlite3.Error:
        return jsonify({"error": "Struktur belum dapat disimpan karena database tidak tersedia."}), 503
    return jsonify({"status": "saved"})


@user_bp.route('/profile-blackowl/photo', methods=['POST'])
def upload_profile_blackowl_photo():
    if not login_required():
        return jsonify({"error": "Silakan login kembali."}), 401
    photo = request.files.get('photo')
    if not photo or not photo.filename:
        return jsonify({"error": "Pilih foto profil terlebih dahulu."}), 400
    extension = os.path.splitext(secure_filename(photo.filename))[1].lower()
    if extension not in {'.jpg', '.jpeg', '.png', '.webp'}:
        return jsonify({"error": "Gunakan foto JPG, PNG, atau WEBP."}), 400
    photo.stream.seek(0, os.SEEK_END)
    if photo.stream.tell() > 2 * 1024 * 1024:
        return jsonify({"error": "Ukuran foto maksimal 2 MB."}), 400
    photo.stream.seek(0)
    photo_dir = os.path.abspath(os.path.join('static', 'uploads', 'blackowl_profiles'))
    os.makedirs(photo_dir, exist_ok=True)
    filename = f'{uuid4().hex}{extension}'
    photo.save(os.path.join(photo_dir, filename))
    return jsonify({"photo_url": url_for('static', filename=f'uploads/blackowl_profiles/{filename}')})


@user_bp.route('/profile-blackowl/export.pdf')
def export_profile_blackowl_pdf():
    if not login_required():
        return redirect(url_for('auth.login'))
    try:
        report = build_blackowl_organization_pdf(get_organization(), os.path.abspath('.'))
    except sqlite3.Error:
        flash('Struktur organisasi belum dapat dimuat karena database tidak tersedia.', 'error')
        return redirect(url_for('user.profile_blackowl'))
    return send_file(report, mimetype='application/pdf', as_attachment=True, download_name='blackowl_organization.pdf')


# ======================
# PENTEST LIST + CREATE
# ======================
# @user_bp.route('/pentest')
# def pentest():
#     if not login_required():
#         return redirect(url_for('auth.login'))

#     level = session.get("level")

#     if level == "Internal":
#         page = request.args.get('page', 1, type=int)
#         keyword = request.args.get('keyword', '', type=str)
#         per_page = 5

#         pentests, total = search_pentest_internal(keyword, page, per_page)

#         total_pages = (total + per_page - 1) // per_page

#         return render_template(
#             'internal/pentest.html',
#             pentests=pentests,
#             page=page,
#             total_pages=total_pages,
#             keyword=keyword
#         )

#     # eksternal tetap
#     user_id = session.get("user_id")
#     pentests = get_pentest_by_user(user_id)

#     return render_template('user/pentest.html', pentests=pentests)
@user_bp.route('/pentest')
def pentest():
    if not login_required():
        return redirect(url_for('auth.login'))

    level = session.get("level")

    if level == "Internal":
        keyword = request.args.get('keyword', '', type=str)
        status_filter = request.args.get('status', '', type=str).strip()
        page = max(request.args.get('page', 1, type=int), 1)
        per_page = 10
        valid_statuses = {'Pending', 'In Progress', 'Done', 'Cancel'}
        if status_filter not in valid_statuses:
            status_filter = ''
        db_error = None
        summary = {"total_assets": 0, "pending": 0, "in_progress": 0, "done": 0, "cancel": 0}
        try:
            pentests = get_pentest_register(keyword)
            summary = get_pentest_register_summary()
            if status_filter:
                pentests = [pentest for pentest in pentests if pentest['pentest_status'] == status_filter]
        except sqlite3.Error:
            # Keep the Pentest page available when the SQL Server is temporarily
            # unreachable. Other modules and their database behavior are untouched.
            pentests = []
            db_error = "Data Pentest belum dapat dimuat karena koneksi database sedang tidak tersedia. Silakan coba lagi beberapa saat lagi."

        total_pentests = len(pentests)
        total_pages = max((total_pentests + per_page - 1) // per_page, 1)
        page = min(page, total_pages)
        start_index = (page - 1) * per_page
        visible_pentests = pentests[start_index:start_index + per_page]

        return render_template(
            'internal/pentest.html',
            pentests=visible_pentests,
            keyword=keyword,
            summary=summary,
            status_filter=status_filter,
            db_error=db_error,
            page=page,
            per_page=per_page,
            total_pentests=total_pentests,
            total_pages=total_pages,
            showing_from=start_index + 1 if total_pentests else 0,
            showing_to=min(start_index + per_page, total_pentests),
        )

    # eksternal tetap
    user_id = session.get("user_id")
    db_error = None
    try:
        pentests = get_pentest_by_user(user_id)
    except sqlite3.Error:
        pentests = []
        db_error = "Data Pentest belum dapat dimuat karena koneksi database sedang tidak tersedia. Silakan coba lagi beberapa saat lagi."

    return render_template('user/pentest.html', pentests=pentests, db_error=db_error)


# ======================
# CREATE / EDIT (EKSTERNAL ONLY)
# ======================
@user_bp.route('/pentest/edit/<int:id>', methods=['GET', 'POST'])
def edit_pentest(id):
    if not login_required():
        return redirect(url_for('auth.login'))

    user_id = session.get("user_id")

    # CREATE
    if id == 0:
        if request.method == 'POST':
            data = {
                "user_id": user_id,
                "nama_project": request.form["nama_project"],
                "deskripsi": request.form.get("deskripsi"),
                "target_url": request.form.get("target_url"),
                "environment": request.form.get("environment"),
                "start_date": request.form.get("start_date"),
                "end_date": request.form.get("end_date"),
                "link_app": request.form.get("link_app"),
                "link_document": request.form.get("link_document"),
                "catatan_user": request.form.get("catatan_user")
            }
            create_pentest(data)
            return redirect(url_for('user.pentest'))

        return render_template('user/pentest_form.html', pentest=None)

    # EDIT
    pentest = get_pentest_by_id(id)
    if not pentest:
        return redirect(url_for('user.pentest'))

    # 🔒 hanya miliknya
    if pentest["user_id"] != user_id:
        return redirect(url_for('user.pentest'))

    # 🔒 hanya boleh edit saat To_Do
    if pentest["status"] != "To_Do":
        return redirect(url_for('user.pentest'))

    if request.method == 'POST':
        data = {
            "id": id,
            "nama_project": request.form["nama_project"],
            "deskripsi": request.form.get("deskripsi"),
            "target_url": request.form.get("target_url"),
            "environment": request.form.get("environment"),
            "start_date": request.form.get("start_date"),
            "end_date": request.form.get("end_date"),
            "link_app": request.form.get("link_app"),
            "link_document": request.form.get("link_document"),
            "catatan_user": request.form.get("catatan_user")
        }
        update_pentest(data)
        return redirect(url_for('user.pentest'))

    return render_template('user/pentest_form.html', pentest=pentest)


# ======================
# DETAIL
# ======================
@user_bp.route('/pentest/detail/<int:id>')
def pentest_detail(id):
    if not login_required():
        return redirect(url_for('auth.login'))

    pentest = get_pentest_by_id(id)

    if not pentest:
        return redirect(url_for('user.pentest'))

    # 🔥 IZINKAN INTERNAL MELIHAT SEMUA
    if session.get("level") == "Internal":
        return render_template('user/pentest_detail.html', pentest=pentest)

    # EKSTERNAL → hanya miliknya
    if pentest["user_id"] != session.get("user_id"):
        return redirect(url_for('user.pentest'))

    return render_template('user/pentest_detail.html', pentest=pentest)


# ======================
# DELETE (DIMATIKAN)
# ======================
# @user_bp.route('/pentest/delete/<int:id>', methods=['POST'])
# def delete_pentest_route(id):
#     return redirect(url_for('user.pentest'))
@user_bp.route('/pentest/internal/delete/<int:id>', methods=['POST'])
def delete_pentest_internal(id):
    if not login_required():
        return redirect(url_for('auth.login'))

    # 🔒 hanya internal
    if session.get("level") != "Internal":
        return redirect(url_for('user.pentest'))

    delete_pentest_by_id(id)
    return redirect(url_for('user.pentest'))




def is_admin():
    return session.get("level") == "Admin"

def is_internal():
    return session.get("level") == "Internal"

def is_eksternal():
    return session.get("level") == "Eksternal"

@user_bp.route('/pentest/internal/edit/<int:id>', methods=['GET', 'POST'])
def edit_pentest_internal(id):
    if not login_required():
        return redirect(url_for('auth.login'))

    if session.get("level") != "Internal":
        return redirect(url_for('user.pentest'))

    pentest = get_pentest_by_id(id)

    if not pentest:
        return redirect(url_for('user.pentest'))

    users = get_all_users_for_dropdown()
    current_owner = next(
        (user for user in users if user["id"] == pentest["user_id"]),
        None
    )
    owner_value = pentest.get("manual_owner_name") or (
        current_owner["nama"] if current_owner else ""
    )

    if request.method == 'POST':
        owner_name = request.form.get("owner_name", "").strip() or request.form.get("owner_existing", "").strip()

        if not owner_name:
            flash("Owner wajib diisi.", "error")
            return render_template(
                'internal/pentest_edit.html',
                pentest=pentest,
                users=users,
                current_owner=current_owner,
                owner_value=owner_value
            ), 400

        selected_owner = next(
            (user for user in users if user["nama"].casefold() == owner_name.casefold()),
            None
        )

        # Prioritize a typed free-text owner, but if it matches an existing user,
        # use that user record. Otherwise store the typed value in manual_owner_name.
        owner_id = selected_owner["id"] if selected_owner else pentest["user_id"]
        manual_owner_name = None if selected_owner else owner_name

        data = {
            "id": id,
            "user_id": owner_id,
            "manual_owner_name": manual_owner_name,
            "status": request.form.get("status"),
            "start_date": request.form.get("start_date"),
            "end_date": request.form.get("end_date"),
            "link_document": request.form.get("link_document"),
            "catatan_internal": request.form.get("catatan_internal")
        }

        update_pentest_internal(data)
        return redirect(url_for('user.pentest'))

    return render_template(
        'internal/pentest_edit.html',
        pentest=pentest,
        users=users,
        current_owner=current_owner,
        owner_value=owner_value
    )

@user_bp.route('/pentest/internal/create', methods=['GET', 'POST'])
def create_pentest_internal():
    if not login_required():
        return redirect(url_for('auth.login'))

    # 🔒 hanya internal
    if session.get("level") != "Internal":
        return redirect(url_for('user.pentest'))

    if request.method == 'POST':
        report = request.files.get("report_document")
        report_data = {"report_original_name": None, "report_file_path": None, "report_file_type": None, "report_file_size": None}
        if report and report.filename:
            extension = report.filename.rsplit('.', 1)[-1].lower() if '.' in report.filename else ''
            allowed = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'csv'}
            if extension not in allowed:
                flash("Format laporan harus PDF, DOC/DOCX, Excel, atau CSV.", "error")
                return redirect(url_for('user.create_pentest_internal'))
            report_dir = os.path.join('uploads', 'pentest')
            os.makedirs(report_dir, exist_ok=True)
            filename = f"PENTEST_{uuid4().hex}.{extension}"
            full_path = os.path.join(report_dir, filename)
            report.save(full_path)
            report_data = {"report_original_name": secure_filename(report.filename), "report_file_path": full_path,
                           "report_file_type": extension, "report_file_size": os.path.getsize(full_path)}

        data = {
            # Kept only for compatibility with the existing pentest_tasks table;
            # the register UI uses Requested as the user-facing submitter field.
            "user_id": session.get("user_id"),
            "requested_by": request.form.get("requested_by", "").strip(),
            "nama_project": request.form.get("nama_project"),
            "menu_items": request.form.get("menu_items"),
            "va_status": request.form.get("va_status"),
            "pentest_status": request.form.get("pentest_status"),
            "pentest_tracker_url": request.form.get("pentest_tracker_url"),
            "date_req": request.form.get("date_req"),
            "date_target": request.form.get("date_target"),
            **report_data,
        }
        try:
            create_pentest_register(data)
        except sqlite3.Error:
            if report_data["report_file_path"] and os.path.isfile(report_data["report_file_path"]):
                os.remove(report_data["report_file_path"])
            flash("Request Pentest belum dapat disimpan. Silakan coba kembali atau hubungi administrator aplikasi.", "error")
            return redirect(url_for('user.create_pentest_internal'))

        # log
        from flask import g
        g.log_action = "CREATE_PENTEST_INTERNAL"
        g.log_detail = f"project={data['nama_project']}"

        flash("Request Pentest berhasil disimpan.", "success")
        return redirect(url_for('user.pentest'))

    return render_template('internal/pentest_create.html')


def _get_pentest_report_file(pentest_id):
    """Find a stored Pentest report and normalize its path for Flask."""
    report = get_pentest_report(pentest_id)
    if not report or not report.report_file_path:
        return None

    # Existing records store paths relative to the project root (uploads/...).
    # send_file otherwise resolves them from app/, causing a file-not-found error.
    report_path = os.path.abspath(report.report_file_path)
    if not os.path.isfile(report_path):
        return None

    filename = secure_filename(report.report_original_name or '') or f'pentest_report_{pentest_id}'
    return report_path, filename


@user_bp.route('/pentest/internal/report/<int:id>/view')
def view_pentest_report(id):
    if not login_required() or session.get("level") != "Internal":
        return redirect(url_for('auth.login'))
    report_file = _get_pentest_report_file(id)
    if not report_file:
        return "Dokumen laporan tidak ditemukan.", 404
    report_path, filename = report_file
    mimetype = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    return send_file(report_path, mimetype=mimetype, as_attachment=False, download_name=filename)


@user_bp.route('/pentest/internal/report/<int:id>/download')
def download_pentest_report(id):
    if not login_required() or session.get("level") != "Internal":
        return redirect(url_for('auth.login'))
    report_file = _get_pentest_report_file(id)
    if not report_file:
        return "Dokumen laporan tidak ditemukan.", 404
    report_path, filename = report_file
    return send_file(report_path, as_attachment=True, download_name=filename)


@user_bp.route('/pentest/internal/register-report.pdf')
def download_pentest_register_report():
    """Export every registered Pentest request and its tracker into one PDF."""
    if not login_required() or session.get("level") != "Internal":
        return redirect(url_for('auth.login'))
    pentests = get_pentest_register()
    for pentest in pentests:
        pentest["tracker_items"] = get_pentest_tracker_items(pentest["id"])
    report = build_pentest_register_report(pentests, get_pentest_register_summary())
    filename = f"pentest_register_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(report, mimetype='application/pdf', as_attachment=True, download_name=filename)


@user_bp.route('/pentest/internal/view/<int:id>')
def view_pentest_register(id):
    if not login_required() or session.get("level") != "Internal":
        return redirect(url_for('auth.login'))
    pentest = get_pentest_register_by_id(id)
    if not pentest:
        flash("Data Pentest tidak ditemukan.", "error")
        return redirect(url_for('user.pentest'))
    tracker_items = get_pentest_tracker_items(id)
    tracker_progress = round(sum(item['progress'] for item in tracker_items) / len(tracker_items)) if tracker_items else 0
    return render_template('internal/pentest_view.html', pentest=pentest, tracker_items=tracker_items,
                           tracker_progress=tracker_progress)


def _tracker_item_data(form):
    title = form.get('title', '').strip()
    status = form.get('status', 'Planned')
    allowed_statuses = {'Planned', 'In Progress', 'Blocked', 'Completed'}
    if not title:
        raise ValueError('Nama tahapan tracker wajib diisi.')
    if status not in allowed_statuses:
        raise ValueError('Status tracker tidak valid.')
    try:
        progress = int(form.get('progress', 0))
    except (TypeError, ValueError):
        raise ValueError('Progress harus berupa angka antara 0 sampai 100.')
    if not 0 <= progress <= 100:
        raise ValueError('Progress harus bernilai antara 0 sampai 100.')
    return {
        'title': title,
        'status': status,
        'progress': progress,
        'target_date': form.get('target_date') or None,
        'notes': form.get('notes', '').strip() or None,
    }


@user_bp.route('/pentest/internal/tracker/<int:id>')
def pentest_tracker(id):
    if not login_required() or session.get('level') != 'Internal':
        return redirect(url_for('auth.login'))
    pentest = get_pentest_register_by_id(id)
    if not pentest:
        flash('Data Pentest tidak ditemukan.', 'error')
        return redirect(url_for('user.pentest'))
    items = get_pentest_tracker_items(id)
    total_progress = round(sum(item['progress'] for item in items) / len(items)) if items else 0
    completed_items = sum(item['status'] == 'Completed' for item in items)
    return render_template('internal/pentest_tracker.html', pentest=pentest, items=items,
                           total_progress=total_progress, completed_items=completed_items)


@user_bp.route('/pentest/internal/tracker/<int:id>/report.pdf')
def download_pentest_tracker_report(id):
    if not login_required() or session.get('level') != 'Internal':
        return redirect(url_for('auth.login'))
    pentest = get_pentest_register_by_id(id)
    if not pentest:
        flash('Data Pentest tidak ditemukan.', 'error')
        return redirect(url_for('user.pentest'))
    items = get_pentest_tracker_items(id)
    total_progress = round(sum(item['progress'] for item in items) / len(items)) if items else 0
    completed_items = sum(item['status'] == 'Completed' for item in items)
    report = build_pentest_tracker_report(pentest, items, total_progress, completed_items)
    filename = f"pentest_tracker_{id}.pdf"
    return send_file(report, mimetype='application/pdf', as_attachment=True, download_name=filename)


@user_bp.route('/pentest/internal/tracker/<int:id>/items', methods=['POST'])
def create_pentest_tracker_item_route(id):
    if not login_required() or session.get('level') != 'Internal':
        return redirect(url_for('auth.login'))
    if not get_pentest_register_by_id(id):
        flash('Data Pentest tidak ditemukan.', 'error')
        return redirect(url_for('user.pentest'))
    try:
        create_pentest_tracker_item(id, _tracker_item_data(request.form))
        flash('Tahapan tracker berhasil ditambahkan.', 'success')
    except ValueError as error:
        flash(str(error), 'error')
    return redirect(url_for('user.pentest_tracker', id=id))


@user_bp.route('/pentest/internal/tracker/<int:id>/items/<int:item_id>', methods=['POST'])
def update_pentest_tracker_item_route(id, item_id):
    if not login_required() or session.get('level') != 'Internal':
        return redirect(url_for('auth.login'))
    try:
        update_pentest_tracker_item(item_id, id, _tracker_item_data(request.form))
        flash('Tahapan tracker berhasil diperbarui.', 'success')
    except ValueError as error:
        flash(str(error), 'error')
    return redirect(url_for('user.pentest_tracker', id=id))


@user_bp.route('/pentest/internal/tracker/<int:id>/items/<int:item_id>/delete', methods=['POST'])
def delete_pentest_tracker_item_route(id, item_id):
    if not login_required() or session.get('level') != 'Internal':
        return redirect(url_for('auth.login'))
    delete_pentest_tracker_item(item_id, id)
    flash('Tahapan tracker berhasil dihapus.', 'success')
    return redirect(url_for('user.pentest_tracker', id=id))


@user_bp.route('/pentest/internal/edit-register/<int:id>', methods=['GET', 'POST'])
def edit_pentest_register_route(id):
    if not login_required() or session.get("level") != "Internal":
        return redirect(url_for('auth.login'))
    pentest = get_pentest_register_by_id(id)
    if not pentest:
        flash("Data Pentest tidak ditemukan.", "error")
        return redirect(url_for('user.pentest'))
    if request.method == 'POST':
        report = request.files.get('report_document')
        file_data = {"report_original_name": None, "report_file_path": None, "report_file_type": None, "report_file_size": None}
        if report and report.filename:
            extension = report.filename.rsplit('.', 1)[-1].lower() if '.' in report.filename else ''
            if extension not in {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'csv'}:
                flash("Format laporan harus PDF, DOC/DOCX, Excel, atau CSV.", "error")
                return redirect(request.url)
            report_dir = os.path.join('uploads', 'pentest'); os.makedirs(report_dir, exist_ok=True)
            filename = f"PENTEST_{uuid4().hex}.{extension}"; full_path = os.path.join(report_dir, filename)
            report.save(full_path)
            file_data = {"report_original_name": secure_filename(report.filename), "report_file_path": full_path,
                         "report_file_type": extension, "report_file_size": os.path.getsize(full_path)}
        data = {"requested_by": request.form.get('requested_by', '').strip(), "nama_project": request.form.get('nama_project'),
                "menu_items": request.form.get('menu_items'), "va_status": request.form.get('va_status'),
                "pentest_status": request.form.get('pentest_status'), "pentest_tracker_url": pentest.pentest_tracker_url,
                "date_req": request.form.get('date_req'), "date_target": request.form.get('date_target'), **file_data}
        update_pentest_register(id, data)
        if file_data['report_file_path'] and pentest.report_file_path and os.path.isfile(pentest.report_file_path):
            os.remove(pentest.report_file_path)
        flash("Request Pentest berhasil diperbarui.", "success")
        return redirect(url_for('user.view_pentest_register', id=id))
    return render_template('internal/pentest_edit_register.html', pentest=pentest)


@user_bp.route('/pentest/internal/delete-register/<int:id>', methods=['POST'])
def delete_pentest_register_route(id):
    if not login_required() or session.get("level") != "Internal":
        return redirect(url_for('auth.login'))
    record = delete_pentest_register(id)
    if record and record.report_file_path and os.path.isfile(record.report_file_path):
        os.remove(record.report_file_path)
    flash("Request Pentest berhasil dihapus.", "success")
    return redirect(url_for('user.pentest'))

@user_bp.route('/ip_intelligence')
def ip_intelligence():

    if not login_required():
        return redirect(
            url_for('auth.login')
        )

    page = request.args.get(
        'page',
        1,
        type=int
    )

    keyword = request.args.get(
        'keyword',
        ''
    )

    per_page = 10

    if keyword:

        data, total = search_ip(
            keyword,
            page,
            per_page
        )

    else:

        data, total = get_all_ip(
            page,
            per_page
        )

    summary = get_ip_summary()

    total_pages = (
        total + per_page - 1
    ) // per_page

    return render_template(
        'user/ip_intelligence.html',

        data=data,
        page=page,
        total_pages=total_pages,
        keyword=keyword,

        total_ip=summary["total_ip"],
        total_block=summary["total_block"],
        total_allow=summary["total_allow"]
    )
    
@user_bp.route('/ip_intelligence/upload', methods=['POST'])
def upload_ip():

    if not login_required():
        return redirect(url_for('auth.login'))

    try:

        print("=" * 50)
        print("UPLOAD IP INTELLIGENCE START")
        print("=" * 50)

        file = request.files.get('file')

        if not file:
            print("ERROR: FILE NOT FOUND")
            return redirect(url_for('user.ip_intelligence'))

        print(f"FILE NAME: {file.filename}")

        filename = file.filename.lower()

        # READ FILE
        if filename.endswith('.csv'):

            try:

                df = pd.read_csv(
                    file,
                    sep=';'
                )

            except:

                file.seek(0)

                df = pd.read_csv(file)

        elif filename.endswith('.xlsx') or filename.endswith('.xls'):

            df = pd.read_excel(file)

        else:

            print("ERROR: INVALID FILE FORMAT")

            return redirect(
                url_for('user.ip_intelligence')
            )

        print("ORIGINAL HEADER:")
        print(df.columns.tolist())

        # NORMALIZE HEADER
        df.columns = (
            df.columns
            .str.strip()
            .str.lower()
            .str.replace(" ", "_")
        )

        print("NORMALIZED HEADER:")
        print(df.columns.tolist())

        required_columns = [
            'blacklisted_address',
            'description',
            'status'
        ]

        for col in required_columns:

            if col not in df.columns:

                print(
                    f"ERROR: COLUMN '{col}' NOT FOUND"
                )

                return redirect(
                    url_for('user.ip_intelligence')
                )

        success_count = 0
        failed_count = 0

        for index, row in df.iterrows():

            try:

                blacklisted_address = str(
                    row['blacklisted_address']
                ).strip()

                description = str(
                    row['description']
                ).strip()

                status = str(
                    row['status']
                ).strip()

                print(
                    f"INSERT ROW {index+1}: "
                    f"{blacklisted_address}"
                )

                insert_ip(
                    blacklisted_address,
                    description,
                    status
                )

                success_count += 1

            except Exception as row_error:

                failed_count += 1

                print(
                    f"FAILED ROW {index+1}"
                )

                print(str(row_error))

        print("=" * 50)
        print(
            f"IMPORT FINISHED | "
            f"SUCCESS={success_count} "
            f"FAILED={failed_count}"
        )
        print("=" * 50)

    except Exception as e:

        print("=" * 50)
        print("IMPORT ERROR")
        print("=" * 50)
        print(str(e))

    return redirect(
        url_for('user.ip_intelligence')
    )
    
@user_bp.route('/ip_intelligence/add')
def ip_add():

    if not login_required():
        return redirect(url_for('auth.login'))

    return render_template(
        'user/ip_intelligence_add.html'
    )
    
    
@user_bp.route(
    '/ip_intelligence/save',
    methods=['POST']
)
def ip_save():

    if not login_required():
        return redirect(url_for('auth.login'))

    blacklisted_address = request.form.get(
        'blacklisted_address'
    )

    description = request.form.get(
        'description'
    )

    status = request.form.get(
        'status'
    )

    insert_ip(
        blacklisted_address,
        description,
        status
    )

    return redirect(
        url_for('user.ip_intelligence')
    )
    
@user_bp.route(
    '/ip_intelligence/edit/<int:ip_id>'
)
def ip_edit(ip_id):

    if not login_required():
        return redirect(
            url_for('auth.login')
        )

    ip_data = get_ip_by_id(ip_id)

    return render_template(
        'user/ip_intelligence_edit.html',
        ip=ip_data
    )
    
@user_bp.route(
    '/ip_intelligence/update/<int:ip_id>',
    methods=['POST']
)
def ip_update(ip_id):

    if not login_required():
        return redirect(
            url_for('auth.login')
        )

    update_ip(

        ip_id,

        request.form.get(
            'blacklisted_address'
        ),

        request.form.get(
            'description'
        ),

        request.form.get(
            'status'
        )
    )

    return redirect(
        url_for(
            'user.ip_intelligence'
        )
    )
