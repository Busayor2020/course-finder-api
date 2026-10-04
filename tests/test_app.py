import pytest

from app import create_app
from app.config import ProductionConfig


def test_unknown_environment_name_fails_fast():
    with pytest.raises(RuntimeError, match="Unknown FLASK_ENV 'staging'"):
        create_app("staging")


def test_production_refuses_to_start_without_secrets(monkeypatch):
    # Simulate a server whose .env is missing both values.
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", None)
    monkeypatch.setattr(ProductionConfig, "SQLALCHEMY_DATABASE_URI", None)

    with pytest.raises(RuntimeError, match="SECRET_KEY, SQLALCHEMY_DATABASE_URI"):
        create_app("production")


def test_production_has_debug_off(monkeypatch):
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "x")
    monkeypatch.setattr(ProductionConfig, "SQLALCHEMY_DATABASE_URI", "sqlite://")

    assert create_app("production").debug is False
