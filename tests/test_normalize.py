from decimal import Decimal

import pytest

from app.ingest.normalize import (
    normalize_country,
    normalize_level,
    normalize_study_mode,
    parse_duration_months,
    parse_fee,
    parse_ielts,
    parse_intakes,
    row_hash,
    slugify,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("UK", "UK"),
        ("United Kingdom", "UK"),
        ("  england ", "UK"),
        ("Scotland", "UK"),
        ("Canada", "CA"),
        ("CA", "CA"),
        ("CANADA", "CA"),
        ("France", None),
        ("", None),
    ],
)
def test_normalize_country(raw, expected):
    assert normalize_country(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("MSc", "Masters"),
        ("MA", "Masters"),
        ("Master's", "Masters"),
        ("masters", "Masters"),
        ("BSc (Hons)", "Undergraduate"),
        ("BEng (hons)", "Undergraduate"),
        ("Undergraduate", "Undergraduate"),
        ("PhD", "PhD"),
        ("Doctorate", "PhD"),
        ("Foundation Year", "Foundation"),
        ("Diploma", None),
    ],
)
def test_normalize_level(raw, expected):
    assert normalize_level(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("Full-time", "full_time"), ("FT", "full_time"), ("", "full_time"), ("part time", "part_time"),
     ("weekends", None)],
)  # fmt: skip
def test_normalize_study_mode(raw, expected):
    assert normalize_study_mode(raw) == expected


@pytest.mark.parametrize(
    ("raw", "country", "expected"),
    [
        ("£18,500", None, (Decimal("18500.00"), "GBP")),
        ("18500", "UK", (Decimal("18500.00"), "GBP")),
        ("GBP 18,500.50", None, (Decimal("18500.50"), "GBP")),
        ("CAD 32,000", None, (Decimal("32000.00"), "CAD")),
        ("$29,450", None, (Decimal("29450.00"), "CAD")),
        ("C$31,200", None, (Decimal("31200.00"), "CAD")),
        ("29450", "CA", (Decimal("29450.00"), "CAD")),
        ("-500", "UK", (Decimal("-500.00"), "GBP")),
        ("TBC", "UK", (None, "GBP")),
        ("", "CA", (None, "CAD")),
    ],
)
def test_parse_fee(raw, country, expected):
    assert parse_fee(raw, country) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("6.5", Decimal("6.5")), ("7", Decimal("7.0")), ("12", Decimal("12.0")), ("abc", None),
     ("NaN", None), ("", None)],
)  # fmt: skip
def test_parse_ielts(raw, expected):
    assert parse_ielts(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("12", 12), ("12 months", 12), ("1 year", 12), ("2 Years", 24), ("soon", None)],
)
def test_parse_duration_months(raw, expected):
    assert parse_duration_months(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("September", ["September"]),
        ("Sept; Jan", ["January", "September"]),
        ("september, january, Sept", ["January", "September"]),
        ("sep/jan/may", ["January", "May", "September"]),
        ("", []),
        ("Spring", None),
        ("Ju", None),
    ],
)
def test_parse_intakes(raw, expected):
    assert parse_intakes(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("University of Leeds", "university-of-leeds"),
        ("Université de Montréal", "universite-de-montreal"),
        ("King's College London", "kings-college-london"),
        ("Accounting & Finance", "accounting-and-finance"),
        ("  Data   Science ", "data-science"),
    ],
)
def test_slugify(raw, expected):
    assert slugify(raw) == expected


def course_fields(**overrides):
    fields = {
        "title": "Data Science",
        "subject_area": "Computer Science",
        "duration_months": 12,
        "study_mode": "full_time",
        "intakes": ["January", "September"],
        "tuition_fee_international": Decimal("18500.00"),
        "currency": "GBP",
        "ielts_min": Decimal("6.5"),
        "source_url": None,
    }
    return fields | overrides


def test_row_hash_is_stable_and_ignores_non_business_fields():
    assert row_hash(course_fields()) == row_hash(course_fields())
    assert row_hash(course_fields()) == row_hash(course_fields() | {"university_name": "x"})
    assert len(row_hash(course_fields())) == 64


def test_row_hash_changes_when_a_business_field_changes():
    changed = course_fields(tuition_fee_international=Decimal("18600.00"))

    assert row_hash(course_fields()) != row_hash(changed)
