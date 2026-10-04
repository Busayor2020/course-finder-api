from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event

from app import create_app
from app.extensions import db
from app.models import Course, IngestionRun, University, utcnow


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


@pytest.fixture
def seeded(app):
    """A small, known catalogue: 2 UK and 1 Canadian university, 6 courses."""
    leeds = University(
        name="University of Leeds", slug="university-of-leeds", country="UK", city="Leeds"
    )
    glasgow = University(
        name="University of Glasgow", slug="university-of-glasgow", country="UK", city="Glasgow"
    )
    toronto = University(
        name="University of Toronto", slug="university-of-toronto", country="CA", city="Toronto"
    )
    now = utcnow()

    def course(university, title, level, subject, fee, ielts, intakes, verified_days_ago=0):
        currency = "GBP" if university.country == "UK" else "CAD"
        return Course(
            university=university,
            title=title,
            slug=title.lower().replace(" ", "-"),
            level=level,
            subject_area=subject,
            intakes=intakes,
            currency=currency,
            tuition_fee_international=Decimal(fee),
            ielts_min=Decimal(ielts),
            content_hash="0" * 64,
            last_verified_at=now - timedelta(days=verified_days_ago),
        )

    db.session.add_all([
        course(leeds, "Data Science", "Masters", "Computer Science", "18500", "6.5",
               ["January", "September"]),
        course(leeds, "Data Science", "PhD", "Computer Science", "24000", "7.0", ["September"]),
        course(leeds, "Law", "Undergraduate", "Law", "22000", "6.5", ["September"],
               verified_days_ago=45),
        course(glasgow, "Business Analytics", "Masters", "Business", "26000", "6.5",
               ["September"]),
        course(toronto, "Computer Science", "Undergraduate", "Computer Science", "58000", "6.5",
               ["January", "May", "September"]),
        course(toronto, "Public Health", "Masters", "Health", "35000", "7.0", ["September"]),
        IngestionRun(source_file="data/sample_courses.csv", status="success", rows_read=6,
                     inserted=6, finished_at=now),
    ])  # fmt: skip
    db.session.commit()
