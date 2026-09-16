"""Production WSGI entry point for Waitress/IIS-compatible hosting."""
from app import create_app


app = create_app()
