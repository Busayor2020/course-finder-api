import pytest

from app import create_app
from app.extensions import db


@pytest.fixture
def app():
    app = create_app("testing")
    # Tests skip Alembic and build the schema straight from the models.
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
