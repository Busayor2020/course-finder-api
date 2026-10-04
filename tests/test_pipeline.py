import csv
import re

import pytest

from app.extensions import db
from app.ingest.pipeline import run_ingestion
from app.models import Course, IngestionRun, University

HEADER = [
    "University Name", "Country", "City", "Website", "Title", "Level", "Subject Area",
    "Duration Months", "Study Mode", "Intakes", "Tuition Fee (International)", "IELTS Min",
    "Source URL",
]  # fmt: skip
LEEDS = ["University of Leeds", "England", "Leeds", "https://www.leeds.ac.uk"]
TORONTO = ["University of Toronto", "Canada", "Toronto", "https://www.utoronto.ca"]

VALID_ROWS = [
    LEEDS + ["Data Science", "MSc", "Computer Science", "12", "FT", "Sept; Jan", "£18,500",
             "6.5", ""],
    LEEDS + ["  Data Science", "PhD", "Computer Science", "36 months", "", "September", "24000",
             "7", ""],
    TORONTO + ["Computer Science", "BSc", "Computer Science", "4 years", "Full-time", "sep/jan",
               "CAD 58,000", "6.5", ""],
]  # fmt: skip
INVALID_ROWS = [
    LEEDS + ["", "MSc", "Business", "12", "", "September", "£20,000", "6.5", ""],
    LEEDS + ["Finance", "MSc", "Business", "12", "", "September", "-500", "6.5", ""],
    TORONTO + ["Robotics", "Masters", "Engineering", "16", "", "September", "$30,000", "12", ""],
    TORONTO + ["Robotics", "Diploma", "Engineering", "16", "", "September", "$30,000", "6", ""],
]  # fmt: skip
# Same course as the first valid row, with the fee written differently.
DUPLICATE_ROW = LEEDS + ["Data Science", "Masters", "Computer Science", "12", "FT", "Sept; Jan",
                         "18500", "6.5", ""]  # fmt: skip


def write_csv(path, rows):
    with path.open("w", newline="") as file:
        file.write("# synthetic test data\n")
        writer = csv.writer(file)
        writer.writerow(HEADER)
        writer.writerows(rows)
    return path


@pytest.fixture
def sample_csv(tmp_path):
    return write_csv(tmp_path / "courses.csv", VALID_ROWS + INVALID_ROWS + [DUPLICATE_ROW])


def ingest(path, tmp_path):
    return run_ingestion(path, tmp_path / "reports")


def counts(run):
    return {
        "rows_read": run.rows_read,
        "inserted": run.inserted,
        "updated": run.updated,
        "unchanged": run.unchanged,
        "rejected": run.rejected,
        "status": run.status,
    }


def test_first_run_inserts_valid_rows_and_rejects_the_rest(app, sample_csv, tmp_path):
    result = ingest(sample_csv, tmp_path)

    assert counts(result.run) == {
        "rows_read": 8, "inserted": 3, "updated": 0, "unchanged": 0, "rejected": 5,
        "status": "success",
    }  # fmt: skip
    assert db.session.scalar(db.select(db.func.count(University.id))) == 2
    assert db.session.scalar(db.select(db.func.count(Course.id))) == 3


def test_cleaned_values_are_stored(app, sample_csv, tmp_path):
    ingest(sample_csv, tmp_path)

    course = db.session.scalars(db.select(Course).filter_by(slug="computer-science")).one()
    assert course.university.country == "CA"
    assert course.level == "Undergraduate"
    assert course.duration_months == 48
    assert course.intakes == ["January", "September"]
    assert str(course.tuition_fee_international) == "58000.00"
    assert course.currency == "CAD"
    assert course.last_verified_at is not None


def test_rejected_rows_are_reported_with_reasons(app, sample_csv, tmp_path):
    result = ingest(sample_csv, tmp_path)

    with result.report_path.open() as file:
        reasons = [row["reason"] for row in csv.DictReader(file)]
    assert reasons == [
        "title is missing",
        "fee -500.00 must be greater than 0",
        "IELTS 12.0 must be between 4.0 and 9.0",
        "unknown level 'Diploma'",
        "duplicate of row 1",
    ]


def test_second_run_is_fully_unchanged(app, sample_csv, tmp_path):
    ingest(sample_csv, tmp_path)
    first_updated_at = db.session.scalars(db.select(Course.updated_at)).all()

    result = ingest(sample_csv, tmp_path)

    assert counts(result.run) == {
        "rows_read": 8, "inserted": 0, "updated": 0, "unchanged": 3, "rejected": 5,
        "status": "success",
    }  # fmt: skip
    # Re-verifying a course must not count as changing it.
    assert db.session.scalars(db.select(Course.updated_at)).all() == first_updated_at


def test_changed_fee_is_detected_as_one_update(app, tmp_path):
    ingest(write_csv(tmp_path / "v1.csv", VALID_ROWS), tmp_path)
    changed = [row.copy() for row in VALID_ROWS]
    changed[0][10] = "£19,000"

    result = ingest(write_csv(tmp_path / "v2.csv", changed), tmp_path)

    assert (result.run.inserted, result.run.updated, result.run.unchanged) == (0, 1, 2)
    course = db.session.scalars(db.select(Course).filter_by(slug="data-science", level="Masters"))
    assert str(course.one().tuition_fee_international) == "19000.00"


def test_missing_column_marks_the_run_failed(app, tmp_path):
    path = tmp_path / "broken.csv"
    path.write_text("University Name,Title\nUniversity of Leeds,Data Science\n")

    with pytest.raises(ValueError, match="missing required columns"):
        ingest(path, tmp_path)

    run = db.session.scalars(db.select(IngestionRun)).one()
    assert run.status == "failed"
    assert run.finished_at is not None


def test_ingest_command_prints_a_summary(app, sample_csv, tmp_path):
    app.config["REPORTS_DIR"] = str(tmp_path / "reports")

    output = app.test_cli_runner().invoke(args=["ingest", str(sample_csv)]).output

    assert re.search(r"Inserted\s+3\n", output)
    assert re.search(r"Rejected\s+5\n", output)
    assert "Rejected rows and reasons:" in output


def test_sample_csv_rejects_each_bad_row_for_exactly_one_reason(app, tmp_path):
    result = ingest("data/sample_courses.csv", tmp_path)

    assert (result.run.rows_read, result.run.inserted, result.run.rejected) == (200, 185, 15)
    with result.report_path.open() as file:
        reasons = [row["reason"] for row in csv.DictReader(file)]
    # Each invalid sample row exists to demonstrate one problem, so none should
    # trip a second validation rule by accident.
    assert all(";" not in reason for reason in reasons)


def test_report_cells_cannot_run_as_spreadsheet_formulas(app, tmp_path):
    evil = '=HYPERLINK("http://evil.example", "Click")'
    rows = [LEEDS + [evil, "Diploma", "Business", "12", "", "September", "-500", "6.5", ""]]

    result = ingest(write_csv(tmp_path / "evil.csv", rows), tmp_path)

    with result.report_path.open() as file:
        report = next(csv.DictReader(file))
    assert report["title"] == "'" + evil
    assert report["tuition_fee_international"] == "'-500"
    assert report["university_name"] == "University of Leeds"  # normal text is untouched
