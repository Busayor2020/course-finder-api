import os

from flask import Flask

from app.config import config_by_name
from app.extensions import db, migrate


def create_app(config_name: str | None = None) -> Flask:
    """Build and configure a Flask app instance."""
    config_name = config_name or os.environ.get("FLASK_ENV", "production")
    if config_name not in config_by_name:
        raise RuntimeError(f"Unknown FLASK_ENV {config_name!r}; use one of {list(config_by_name)}")

    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    missing = [key for key in ("SECRET_KEY", "SQLALCHEMY_DATABASE_URI") if not app.config.get(key)]
    if missing:
        raise RuntimeError(f"Missing required config: {', '.join(missing)}. See .env.example.")

    db.init_app(app)
    migrate.init_app(app, db)

    # Importing the models registers their tables on db.metadata, which is what
    # `flask db migrate` compares against the live database.
    from app import models  # noqa: F401
    from app.api.health import health_bp

    app.register_blueprint(health_bp)

    from app.cli import ingest_command

    app.cli.add_command(ingest_command)

    return app
