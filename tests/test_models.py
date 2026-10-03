from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Course, University


def make_university(**overrides):
    fields = {"name": "University of Leeds", "slug": "university-of-leeds", "country": "UK"}
    return University(**(fields | overrides))


def make_course(university, **overrides):
    fields = {
        "university": university,
        "title": "Data Science",
        "slug": "data-science",
        "level": "Masters",
        "subject_area": "Computer Science",
        "intakes": ["September", "January"],
        "tuition_fee_international": Decimal("18500.00"),
        "currency": "GBP",
        "ielts_min": Decimal("6.5"),
        "content_hash": "0" * 64,
    }
    return Course(**(fields | overrides))


def test_course_round_trip(app):
    leeds = make_university()
    db.session.add(make_course(leeds))
    db.session.commit()
    db.session.expire_all()

    course = db.session.scalars(db.select(Course)).one()

    assert course.university.slug == "university-of-leeds"
    assert course.intakes == ["September", "January"]
    assert course.tuition_fee_international == Decimal("18500.00")
    assert course.study_mode == "full_time"
    assert course.created_at is not None
    assert leeds.courses == [course]


def test_same_course_slug_and_level_is_rejected_per_university(app):
    leeds = make_university()
    db.session.add_all([make_course(leeds), make_course(leeds)])

    with pytest.raises(IntegrityError):
        db.session.commit()


def test_same_course_slug_allowed_at_another_level(app):
    leeds = make_university()
    db.session.add_all([make_course(leeds), make_course(leeds, level="PhD")])
    db.session.commit()

    assert db.session.scalar(db.select(db.func.count(Course.id))) == 2


def test_unknown_country_is_rejected(app):
    db.session.add(make_university(country="US"))

    with pytest.raises(IntegrityError):
        db.session.commit()
