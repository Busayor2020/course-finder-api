import pytest
from sqlalchemy import event

from app import create_app
from app.extensions import db


def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    # SQLite ignores foreign keys unless each connection switches them on.
    # MySQL always enforces them, so tests must too.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture
def app():
    app = create_app("testing")
    # Tests skip Alembic and build the schema straight from the models.
    with app.app_context():
        event.listen(db.engine, "connect", enable_sqlite_foreign_keys)
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
