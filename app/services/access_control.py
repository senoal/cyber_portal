"""Menu-level authorization for non-admin portal users."""

from flask import session

MENU_OPTIONS = (
    ("dashboard", "Dashboard"),
    ("va_analysis", "Vulnerability — VA Dashboard"),
    ("va_register", "Vulnerability — VA Register & Coverage Tracker"),
    ("pentest", "Pentest"),
    ("ip_intelligence", "IP Intelligence"),
    ("tech", "PDF Manager"),
    ("application_directory", "Direktori Aplikasi"),
    ("tasks", "Tasks"),
    ("organization", "BlackOwl Organization"),
)
MENU_KEYS = {key for key, _ in MENU_OPTIONS}

def default_menu_access(level):
    """Return no access until an administrator grants explicit menu rights.

    ``level`` describes a user's service grouping, not an authorization grant.
    Keeping this compatibility function empty prevents missing configuration
    from accidentally becoming broad access.
    """
    return set()


def menu_for_endpoint(endpoint):
    if endpoint in {"user.dashboard", "user.vulnerability"}:
        return "dashboard"
    # The PDF blueprint is registered as ``pdf_bp``.  Use its real endpoint
    # names here; otherwise direct requests to /pdf/* bypass menu enforcement.
    if endpoint in {"user.va_analysis", "pdf_bp.va_report"}:
        return "va_analysis"
    if endpoint == "pdf_bp.index":
        return "tech"
    if endpoint and endpoint.startswith("va."):
        return "va_register"
    if endpoint and (endpoint.startswith("user.ip_") or endpoint == "user.ip_intelligence"):
        return "ip_intelligence"
    if endpoint and endpoint.startswith("user.tech"):
        return "tech"
    if endpoint and endpoint.startswith("application_directory."):
        return "application_directory"
    if endpoint and endpoint.startswith("tasks."):
        return "tasks"
    if endpoint and endpoint.startswith("user.profile_blackowl"):
        return "organization"
    if endpoint and endpoint.startswith("user."):
        return "pentest"
    return None


def has_menu_access(menu_key):
    return session.get("role") == "admin" or menu_key in set(session.get("menu_access", []))


def landing_endpoint(menu_access):
    """Return the first visible menu endpoint available to the user.

    The order follows ``MENU_OPTIONS``, which is also the order used by the
    sidebar.  This keeps the landing page after login consistent with the
    topmost menu granted to the user.
    """
    endpoints = {
        "dashboard": "user.dashboard",
        "va_analysis": "user.va_analysis",
        "va_register": "va.va_dashboard",
        "pentest": "user.pentest",
        "ip_intelligence": "user.ip_intelligence",
        "tech": "user.tech",
        "application_directory": "application_directory.index",
        "tasks": "tasks.index",
        "organization": "user.profile_blackowl",
    }
    access = set(menu_access)
    for menu_key, _ in MENU_OPTIONS:
        if menu_key in access:
            return endpoints[menu_key]
    return "auth.access_denied"
