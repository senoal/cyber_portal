"""Resilient extraction of VA summary fields from common scanner PDF reports."""

import re
from datetime import datetime

import fitz
from pypdf import PdfReader
from io import BytesIO


SEVERITIES = ("critical", "high", "medium", "low", "info")


def extract_va_fields(pdf_bytes, filename=""):
    text = _extract_text(pdf_bytes)
    if not text.strip():
        raise ValueError("PDF tidak memiliki teks digital. Untuk PDF scan, instal dan konfigurasi Tesseract OCR pada server.")

    profile = _detect_profile(text)
    if profile == "MobSF Android Static Analysis":
        return _extract_mobsf_android_summary(text, filename)

    summary_text = text[:18000]
    if profile == "Greenbone / OpenVAS":
        asset, source = _extract_openvas_target_and_sources(summary_text)
    elif profile == "Pentest Tools Scanner":
        target = _extract_pentest_tools_target(summary_text)
        asset = _host_without_scheme(target)
        source = target or asset
    else:
        target = _extract_target(summary_text, profile)
        asset = _host_without_scheme(target)
        source = target or asset
    counts = _extract_severity_counts(summary_text, profile)
    scan_date = _extract_date(summary_text, profile)
    asset_type = _asset_type(asset, source, filename)
    risk_level = next((level.title() for level in SEVERITIES if counts[level] > 0), "Info")
    missing = [name for name, value in (("Asset", asset), ("Scan Date", scan_date)) if not value]
    confidence = "High" if asset and scan_date and any(counts.values()) else ("Medium" if asset else "Needs review")

    return {
        "scan_date": scan_date,
        "source": source,
        "asset": asset,
        "asset_type": asset_type,
        "critical": counts["critical"],
        "high": counts["high"],
        "medium": counts["medium"],
        "low": counts["low"],
        "info": counts["info"],
        "risk_level": risk_level,
        "report_profile": profile,
        "extraction_confidence": confidence,
        "extraction_note": "Periksa field sebelum simpan." if not missing else f"Perlu diisi manual: {', '.join(missing)}.",
    }


def _extract_text(pdf_bytes):
    chunks = []
    try:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        chunks = [page.get_text("text", sort=True) for page in document]
        document.close()
    except Exception:
        chunks = []
    text = "\n".join(chunks).strip()
    if len(text) >= 80:
        return text
    reader = PdfReader(BytesIO(pdf_bytes))
    fallback = "\n".join(page.extract_text() or "" for page in reader.pages)
    return fallback if len(fallback) > len(text) else text


def _detect_profile(text):
    checks = (
        (r"android\s+static\s+analysis\s+report|report\s+generated\s+by\s*-?\s*mobsf", "MobSF Android Static Analysis"),
        (r"greenbone|open\s*vas|result\s*overview|results\s+per\s+host", "Greenbone / OpenVAS"),
        (r"(?:website|network)\s+vulnerability\s+scanner\s+report", "Pentest Tools Scanner"),
        (r"nessus|tenable", "Tenable Nessus"),
        (r"burp\s*suite|portswigger", "Burp Suite"),
        (r"acunetix|invicti|netsparker", "Acunetix / Invicti"),
    )
    for pattern, profile in checks:
        if re.search(pattern, text, re.I):
            return profile
    return "Pentest / Vulnerability Scanner"


def _extract_mobsf_android_summary(text, filename):
    """Extract the first-summary-page fields of a MobSF Android report.

    MobSF prints the severity captions at the bottom of one page and their
    counters at the top of the following page. Reading the two pages together
    keeps the counters tied to their original order: High, Medium, Info,
    Secure, Hotspot.
    """
    summary = text[:12000]
    app_match = re.search(r"\bApp\s+Name\s*:\s*([^\n]+)", summary, re.I)
    file_match = re.search(r"\bFile\s+Name\s*:\s*([^\n]+)", summary, re.I)
    package_match = re.search(r"\bPackage\s+Name\s*:\s*([^\n]+)", summary, re.I)
    asset = (app_match.group(1).strip() if app_match else "")
    source = (package_match.group(1).strip() if package_match else "")

    # Retain a meaningful, reviewable value if an older MobSF export does not
    # expose App Name, without using the user-uploaded filename as a target.
    if not asset and file_match:
        asset = file_match.group(1).strip()
    if not source:
        source = asset

    scan_date_match = re.search(r"\bScan\s+Date\s*:\s*([^\n]+)", summary, re.I)
    scan_date = _parse_date(scan_date_match.group(1)) if scan_date_match else ""

    # Icon glyphs are embedded between captions in the PDF text. Normalize
    # them before matching the fixed MobSF summary order.
    ascii_summary = re.sub(r"[^\x00-\x7F]+", " ", summary)
    findings_match = re.search(
        r"FINDINGS\s+SEVERITY\s+.*?\bHIGH\b\s+\bMEDIUM\b\s+\bINFO\b\s+\bSECURE\b\s+\bHOTSPOT\b\s+"
        r"(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)",
        ascii_summary,
        re.I | re.S,
    )
    high, medium, info = (0, 0, 0)
    if findings_match:
        high, medium, info = map(int, findings_match.group(1, 2, 3))

    counts = {"critical": 0, "high": high, "medium": medium, "low": 0, "info": info}
    risk_level = next((level.title() for level in SEVERITIES if counts[level] > 0), "Info")
    missing = [name for name, value in (("Asset", asset), ("Scan Date", scan_date)) if not value]
    confidence = "High" if asset and scan_date and findings_match else ("Medium" if asset else "Needs review")

    return {
        "scan_date": scan_date,
        "source": source,
        "asset": asset,
        "asset_type": "Mobile",
        "critical": counts["critical"],
        "high": counts["high"],
        "medium": counts["medium"],
        "low": counts["low"],
        "info": counts["info"],
        "risk_level": risk_level,
        "report_profile": "MobSF Android Static Analysis",
        "extraction_confidence": confidence,
        "extraction_note": (
            "Secure dan Hotspot dari MobSF tidak dimasukkan karena VA Register tidak memiliki field untuk keduanya."
            if not missing else f"Perlu diisi manual: {', '.join(missing)}."
        ),
    }


def _extract_target(text, profile):
    target_patterns = (
        r"(?:scan\s+)?target\s*(?:host)?\s*[:=]\s*(https?://[^\s,;]+|[A-Za-z0-9][A-Za-z0-9._-]*(?:\.[A-Za-z0-9._-]+)*)",
        r"(?:host(?:name)?|asset|scanned\s+host)\s*[:=]\s*(https?://[^\s,;]+|[A-Za-z0-9][A-Za-z0-9._-]*(?:\.[A-Za-z0-9._-]+)*)",
        r"task\s+was\s+(?:run\s+against\s+)?(?:on\s+)?(https?://[^\s,;]+|[A-Za-z0-9][A-Za-z0-9._-]*(?:\.[A-Za-z0-9._-]+)*)",
    )
    for pattern in target_patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1).rstrip(".,)")
    url = re.search(r"https?://[^\s<>)\],]+", text, re.I)
    if url:
        return url.group(0).rstrip(".,)")
    ip = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text)
    if ip:
        return ip.group(0)
    domain = re.search(r"\b(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}\b", text)
    return domain.group(0) if domain else ""


def _extract_pentest_tools_target(text):
    """Read the target printed directly below the Pentest Tools report title."""
    header = text[:1200]
    match = re.search(
        r"(?:Website|Network)\s+Vulnerability\s+Scanner\s+Report\s+(?:\S+\s+){0,8}?"
        r"(https?://[^\s,;]+|(?:\d{1,3}\.){3}\d{1,3})\b",
        header,
        re.I,
    )
    if match:
        return match.group(1).rstrip(".,)")
    # PDF text frequently contains an icon before the target, so inspect only
    # the opening header lines rather than later finding details/references.
    for line in header.splitlines()[:12]:
        ip = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", line)
        if ip:
            return ip.group(0)
        url = re.search(r"https?://[^\s,;]+", line, re.I)
        if url:
            return url.group(0).rstrip(".,)")
    return _extract_target(text, "")


def _extract_openvas_target_and_sources(text):
    """Use the OpenVAS task label for Asset and Result Overview hosts for Source."""
    normalized = re.sub(r"\s+", " ", text)
    task_match = re.search(r"task\s+was\s+['\"“]?(.+?)['\"”]?\s*\.\s*the\s+scan\s+started", normalized, re.I)
    asset = task_match.group(1).strip(" .\"'") if task_match else ""

    overview = re.search(
        r"Host\s+Critical\s+High\s+Medium\s+Low.*?(?=\bTotal\s*:|Vendor\s+security|Results\s+per\s+Host|\Z)",
        text,
        re.I | re.S,
    )
    source_hosts = []
    if overview:
        # Each overview row begins with the scanned host and its severity counters.
        source_hosts = re.findall(
            r"(?m)^\s*((?:\d{1,3}\.){3}\d{1,3}|(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})\s+\d+\s+\d+\s+\d+\s+\d+",
            overview.group(0),
        )
    if not source_hosts:
        source_hosts = re.findall(r"(?m)^\s*\d+\.\d+\s+((?:\d{1,3}\.){3}\d{1,3})\b", text)

    # Preserve document order while eliminating repeat hosts from the contents page.
    unique_hosts = list(dict.fromkeys(source_hosts))
    source = ", ".join(unique_hosts)
    if not asset and source:
        asset = source.split(", ", 1)[0]
    return asset, source or asset


def _extract_severity_counts(text, profile):
    result = {level: 0 for level in SEVERITIES}
    # Prefer an explicit summary block: labels can occur either before or after values.
    for level in SEVERITIES:
        label = r"(?:info|informational?)" if level == "info" else level
        patterns = (
            rf"\b{label}\b\s*[:=\-]?\s*(\d+)\b",
            rf"\b(\d+)\s+{label}\b",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                result[level] = int(match.group(1))
                break

    # OpenVAS Result Overview tables commonly provide one host followed by five counters.
    if profile == "Greenbone / OpenVAS":
        table = re.search(r"(?:host\s+)?critical\s+high\s+medium\s+low(?:\s+log)?\s*(.+?)(?:results\s+per\s+host|\Z)", text, re.I | re.S)
        if table:
            rows = re.findall(r"(?:[A-Za-z0-9._-]+\s+)?(\d+)\s+(\d+)\s+(\d+)\s+(\d+)(?:\s+(\d+))?", table.group(1))
            if rows:
                values = max(rows, key=lambda row: sum(map(int, row[:4])))
                result.update(dict(zip(("critical", "high", "medium", "low", "info"), map(int, values))))
    return result


def _extract_date(text, profile=""):
    if profile == "Greenbone / OpenVAS":
        match = re.search(r"scan\s+started\s+at\s+(?:\w{3}\s+)?([A-Za-z]{3,9}\s+\d{1,2})\s+\d{2}:\d{2}:\d{2}\s+(\d{4})", text, re.I)
        if match:
            for fmt in ("%B %d %Y", "%b %d %Y"):
                try:
                    return datetime.strptime(f"{match.group(1)} {match.group(2)}", fmt).strftime("%Y-%m-%d")
                except ValueError:
                    pass
    patterns = (
        r"(?:scan\s+)?(?:start(?:ed)?\s*(?:time|date)?|scan\s+date|report\s+date|generated\s+(?:on|at))\s*[:=]?\s*([^\n]{6,70})",
        r"(?:Start\s+Time)\s*[:=]?\s*([^\n]{6,70})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            parsed = _parse_date(match.group(1))
            if parsed:
                return parsed
    return _parse_date(text)


def _parse_date(value):
    value = re.sub(r"\s+", " ", value).strip()
    # MobSF writes abbreviated months as e.g. "Feb. 27, 2026".
    value = re.sub(r"\b([A-Za-z]{3})\.", r"\1", value)
    candidates = re.findall(r"(?:\w{3},?\s+)?\w{3,9}\s+\d{1,2},?\s+\d{4}|\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4}", value)
    for candidate in candidates or [value]:
        candidate = re.sub(r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+", "", candidate, flags=re.I)
        for fmt in ("%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y", "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(candidate, fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass
    return ""


def _host_without_scheme(value):
    return re.sub(r"^https?://", "", value, flags=re.I).split("/", 1)[0].split(":", 1)[0]


def _asset_type(asset, source, filename):
    context = f"{asset} {source} {filename}".lower()
    if re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", asset or ""):
        return "Server"
    if "middleware" in context:
        return "Middleware"
    if "mobile" in context or "android" in context or "ios" in context:
        return "Mobile"
    return "Web App"
