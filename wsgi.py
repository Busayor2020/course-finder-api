"""Entry point for Gunicorn (`gunicorn wsgi:app`) and the `flask` CLI."""

from app import create_app

app = create_app()
