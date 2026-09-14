"""Minimal synchronizer-token CSRF protection for form and fetch requests."""

import hmac
import secrets

from flask import abort, request, session


SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
TOKEN_FIELD = "_csrf_token"
TOKEN_HEADER = "X-CSRF-Token"


def csrf_token():
    """Return the current session token, creating it when a page is rendered."""
    token = session.get(TOKEN_FIELD)
    if not token:
        token = secrets.token_urlsafe(32)
        session[TOKEN_FIELD] = token
    return token


def validate_csrf_request():
    """Reject every state-changing request without its matching session token."""
    if request.method in SAFE_METHODS:
        return
    expected = session.get(TOKEN_FIELD)
    provided = request.form.get(TOKEN_FIELD) or request.headers.get(TOKEN_HEADER)
    if not expected or not provided or not hmac.compare_digest(expected, provided):
        abort(400, description="CSRF token tidak valid atau tidak tersedia.")
