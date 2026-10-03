"""Extension objects, created unbound and attached to the app in create_app().

Keeping them here (not in app/__init__.py) lets models and routes import `db`
without importing the app factory, which avoids circular imports.
"""

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
migrate = Migrate()
