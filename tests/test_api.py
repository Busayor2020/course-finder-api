import pytest
from sqlalchemy import event

from app.extensions import db


def get_json(client, url, status=200):
    response = client.get(url)
    assert response.status_code == status, response.get_json()
    return response.get_json()


def titles(body):
    return [(course["title"], course["level"]) for course in body["data"]]


# ---------------------------------------------------------------- universities


def test_universities_are_paginated_and_sorted_by_name(client, seeded):
    body = get_json(client, "/api/v1/universities?per_page=2")

    assert [u["slug"] for u in body["data"]] == ["university-of-glasgow", "university-of-leeds"]
    assert body["meta"] == {"page": 1, "per_page": 2, "total": 3, "pages": 2}


def test_universities_filter_by_country_accepts_aliases(client, seeded):
    body = get_json(client, "/api/v1/universities?country=canada")

    assert [u["slug"] for u in body["data"]] == ["university-of-toronto"]


def test_university_detail_includes_course_count(client, seeded):
    body = get_json(client, "/api/v1/universities/university-of-leeds")

    assert body["data"]["name"] == "University of Leeds"
    assert body["data"]["course_count"] == 3


def test_unknown_university_slug_is_404(client, seeded):
    body = get_json(client, "/api/v1/universities/nowhere", status=404)

    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "No university with slug 'nowhere'."


# --------------------------------------------------------------------- courses


def test_course_list_shape_and_meta(client, seeded):
    body = get_json(client, "/api/v1/courses?per_page=4&page=2")

    assert body["meta"] == {"page": 2, "per_page": 4, "total": 6, "pages": 2}
    assert len(body["data"]) == 2
    course = body["data"][0]
    assert set(course) >= {"id", "title", "level", "tuition_fee_international", "university"}
    assert "content_hash" not in course  # internal fields never leave the API
    assert set(course["university"]) == {"name", "slug", "country", "city"}


def test_money_is_a_string_and_timestamps_are_utc(client, seeded):
    course = get_json(client, "/api/v1/courses?q=public")["data"][0]

    assert course["tuition_fee_international"] == "35000.00"
    assert course["ielts_min"] == "7.0"
    assert course["last_verified_at"].endswith("Z")


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("country=CA", {("Computer Science", "Undergraduate"), ("Public Health", "Masters")}),
        ("level=PhD", {("Data Science", "PhD")}),
        ("level=msc", {("Data Science", "Masters"), ("Business Analytics", "Masters"),
                       ("Public Health", "Masters")}),
        ("subject=Law", {("Law", "Undergraduate")}),
        ("q=SCIENCE", {("Data Science", "Masters"), ("Data Science", "PhD"),
                       ("Computer Science", "Undergraduate")}),
        ("q=health", {("Public Health", "Masters")}),
        ("country=UK&max_fee=22000", {("Data Science", "Masters"), ("Law", "Undergraduate")}),
        ("max_ielts=6.5&country=CA", {("Computer Science", "Undergraduate")}),
        ("intake=may", {("Computer Science", "Undergraduate")}),
        ("intake=January", {("Data Science", "Masters"), ("Computer Science", "Undergraduate")}),
        ("country=UK&level=Masters&intake=September",
         {("Data Science", "Masters"), ("Business Analytics", "Masters")}),
        ("q=100%25", set()),
    ],
)  # fmt: skip
def test_course_filters(client, seeded, query, expected):
    body = get_json(client, f"/api/v1/courses?{query}")

    assert set(titles(body)) == expected
    assert body["meta"]["total"] == len(expected)


def test_blank_filters_are_ignored(client, seeded):
    body = get_json(client, "/api/v1/courses?country=&level=&q=")

    assert body["meta"]["total"] == 6


@pytest.mark.parametrize(
    ("sort", "first", "last"),
    [
        ("title", ("Business Analytics", "Masters"), ("Law", "Undergraduate")),
        ("fee_asc", ("Data Science", "Masters"), ("Business Analytics", "Masters")),
        ("fee_desc", ("Business Analytics", "Masters"), ("Data Science", "Masters")),
    ],
)
def test_course_sorting(client, seeded, sort, first, last):
    # Restricted to the UK so every fee is in the same currency.
    order = titles(get_json(client, f"/api/v1/courses?country=UK&sort={sort}"))

    assert order[0] == first
    assert order[-1] == last


def test_page_past_the_end_is_empty_not_an_error(client, seeded):
    body = get_json(client, "/api/v1/courses?page=50")

    assert body["data"] == []
    assert body["meta"]["total"] == 6


def test_course_list_embeds_universities_without_n_plus_1(client, seeded):
    statements = []

    def record(conn, cursor, statement, *args):
        statements.append(statement)

    event.listen(db.engine, "before_cursor_execute", record)
    try:
        body = get_json(client, "/api/v1/courses")
    finally:
        event.remove(db.engine, "before_cursor_execute", record)

    assert all(course["university"]["name"] for course in body["data"])
    # One COUNT for the meta and one SELECT for the page, however many courses.
    assert len(statements) == 2


def test_course_detail_embeds_full_university(client, seeded):
    course_id = get_json(client, "/api/v1/courses?subject=Law")["data"][0]["id"]

    body = get_json(client, f"/api/v1/courses/{course_id}")

    assert body["data"]["title"] == "Law"
    assert body["data"]["university"]["slug"] == "university-of-leeds"
    assert "website" in body["data"]["university"]


@pytest.mark.parametrize("url", ["/api/v1/courses/9999", "/api/v1/courses/abc", "/api/v1/nope"])
def test_unknown_course_or_route_is_404_json(client, seeded, url):
    body = get_json(client, url, status=404)

    assert body["error"]["code"] == "not_found"


@pytest.mark.parametrize(
    ("query", "field"),
    [
        ("per_page=500", "per_page"),
        ("per_page=0", "per_page"),
        ("page=0", "page"),
        ("max_fee=abc&country=UK", "max_fee"),
        ("max_fee=20000", "max_fee"),  # a fee without a country has no currency
        ("max_ielts=12", "max_ielts"),
        ("level=Diploma", "level"),
        ("country=France", "country"),
        ("intake=Spring", "intake"),
        ("sort=cheapest", "sort"),
        ("contry=UK", "contry"),  # typo'd parameter names are rejected, not ignored
    ],
)
def test_invalid_parameters_are_400(client, seeded, query, field):
    body = get_json(client, f"/api/v1/courses?{query}", status=400)

    assert body["error"]["code"] == "invalid_parameters"
    assert field in body["error"]["details"]
    assert body["error"]["message"].startswith(f"{field}: ")


def test_wrong_method_is_405_json(client):
    response = client.post("/api/v1/courses")

    assert response.status_code == 405
    assert response.get_json()["error"]["code"] == "method_not_allowed"


def test_unexpected_error_is_500_without_internals(client, seeded, monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("database password is hunter2")

    monkeypatch.setattr(db, "paginate", explode)

    body = get_json(client, "/api/v1/courses", status=500)

    assert body == {
        "error": {
            "code": "internal_error",
            "message": "Something went wrong on our side.",
            "details": {},
        }
    }


# ----------------------------------------------------------------------- stats


def test_stats(client, seeded):
    data = get_json(client, "/api/v1/stats")["data"]

    assert data["total_courses"] == 6
    assert data["courses_by_country"] == {"CA": 2, "UK": 4}
    assert data["courses_by_level"] == {"Masters": 3, "PhD": 1, "Undergraduate": 2}
    assert data["stale_courses"] == 1  # Leeds Law was last verified 45 days ago
    assert data["latest_ingestion"]["status"] == "success"


def test_stats_on_an_empty_database(client):
    data = get_json(client, "/api/v1/stats")["data"]

    assert data["total_courses"] == 0
    assert data["latest_ingestion"] is None
