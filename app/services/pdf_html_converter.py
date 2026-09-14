"""PDF-to-HTML conversion that keeps extracted text and page geometry intact."""

from html import escape
from pathlib import Path

try:
    import fitz  # Provided by the PyMuPDF package.
except ImportError:
    fitz = None


MAX_PAGES = 100


def convert_pdf_to_html(source_path, output_path, title):
    if fitz is None:
        raise RuntimeError(
            "Fitur PDF to HTML membutuhkan PyMuPDF. "
            "Administrator server perlu menjalankan: python -m pip install PyMuPDF"
        )
    document = fitz.open(source_path)
    if document.page_count > MAX_PAGES:
        document.close()
        raise ValueError(f"PDF maksimal {MAX_PAGES} halaman.")

    page_markup = []
    for page_number, page in enumerate(document, start=1):
        # PyMuPDF emits positioned HTML using the original font sizes, colors,
        # and page dimensions. No text content is edited during conversion.
        page_markup.append(
            f'<section class="pdf-page" aria-label="Page {page_number}">{page.get_text("html")}</section>'
        )
    document.close()

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><style>
*{{box-sizing:border-box}} body{{margin:0;padding:28px;background:#e9edf2;color:#111;font-family:Arial,sans-serif}}
.pdf-document{{display:flex;flex-direction:column;align-items:center;gap:24px}}
.pdf-page{{position:relative;overflow:hidden;background:#fff;box-shadow:0 10px 28px rgba(15,23,42,.18)}}
.pdf-page>div{{position:relative}} .pdf-page p{{position:absolute;margin:0;white-space:pre-wrap}}
@media print{{body{{padding:0;background:#fff}}.pdf-document{{gap:0}}.pdf-page{{box-shadow:none;break-after:page}}}}
</style></head><body><main class="pdf-document">{''.join(page_markup)}</main></body></html>"""
    destination = Path(output_path).resolve()
    destination.write_text(html, encoding="utf-8")
    return destination
