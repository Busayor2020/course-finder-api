from sqlalchemy.exc import OperationalError

from app.extensions import db


def test_health_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "db": "ok"}


def test_health_reports_db_failure(client, monkeypatch):
    def broken_execute(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(db.session, "execute", broken_execute)

    response = client.get("/health")

    assert response.status_code == 503
    assert response.get_json() == {"status": "degraded", "db": "error"}
