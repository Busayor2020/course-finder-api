from flask import Blueprint, current_app
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db

# Registered without a URL prefix so load balancers and uptime checks can hit /health.
health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        current_app.logger.exception("Health check failed: database unreachable")
        return {"status": "degraded", "db": "error"}, 503
    return {"status": "ok", "db": "ok"}
