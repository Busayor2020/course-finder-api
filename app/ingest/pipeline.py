"""Ingestion pipeline: read a course CSV, clean and validate it, upsert it, report.

Every row read ends up in exactly one bucket, so the counts always add up:
    rows_read = inserted + updated + unchanged + rejected
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pandas as pd
from sqlalchemy import select, update

from app.extensions import db
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
from app.models import Course, IngestionRun, University, utcnow

REQUIRED_COLUMNS = (
    "university_name",
    "country",
    "city",
    "website",
    "title",
    "level",
    "subject_area",
    "duration_months",
    "study_mode",
    "intakes",
    "tuition_fee_international",
    "ielts_min",
    "source_url",
)
# Course columns copied from a cleaned row onto the model on insert or update.
COURSE_FIELDS = (
    "title",
    "subject_area",
    "duration_months",
    "study_mode",
    "intakes",
    "tuition_fee_international",
    "currency",
    "ielts_min",
    "source_url",
)
MAX_FEE = Decimal("1000000")


@dataclass
class Result:
    run: IngestionRun
    report_path: Path | None = None


def read_csv(path: Path) -> pd.DataFrame:
    # dtype=str stops pandas guessing types ("18,500" stays text, "6.0" is not
    # turned into a float), and keep_default_na=False keeps blanks as "" rather
    # than NaN, so every cell is a plain string for the normalisers.
    df = pd.read_csv(path, dtype=str, keep_default_na=False, comment="#")

    # "Tuition Fee (International)" -> "tuition_fee_international"
    df.columns = (
        df.columns.str.strip()
        .str.lower()
        .str.replace(r"[^a-z0-9]+", "_", regex=True)
        .str.strip("_")
    )
    missing = [name for name in REQUIRED_COLUMNS if name not in df.columns]
    if missing:
        raise ValueError(f"CSV is missing required columns: {', '.join(missing)}")

    # Strip the ends and collapse runs of inner whitespace in every cell.
    return df.apply(lambda column: column.str.split().str.join(" "))


def clean_row(raw: dict) -> tuple[dict, list[str]]:
    """Normalise one CSV row. Returns the cleaned row and a list of reasons it
    is invalid (empty when the row is good)."""
    reasons = []
    country = normalize_country(raw["country"])
    level = normalize_level(raw["level"])
    study_mode = normalize_study_mode(raw["study_mode"])
    fee, currency = parse_fee(raw["tuition_fee_international"], country)
    ielts = parse_ielts(raw["ielts_min"])
    duration = parse_duration_months(raw["duration_months"]) if raw["duration_months"] else None
    intakes = parse_intakes(raw["intakes"])

    for column in ("university_name", "title", "subject_area"):
        if not raw[column]:
            reasons.append(f"{column} is missing")
    if country is None:
        reasons.append(f"unknown country {raw['country']!r}")
    if level is None:
        reasons.append(f"unknown level {raw['level']!r}")
    if study_mode is None:
        reasons.append(f"unknown study mode {raw['study_mode']!r}")
    if fee is None:
        reasons.append(f"fee {raw['tuition_fee_international']!r} is not a number")
    elif fee <= 0:
        reasons.append(f"fee {fee} must be greater than 0")
    elif fee >= MAX_FEE:
        reasons.append(f"fee {fee} is implausibly large")
    if raw["ielts_min"] and ielts is None:
        reasons.append(f"IELTS {raw['ielts_min']!r} is not a number")
    elif ielts is not None and not Decimal("4.0") <= ielts <= Decimal("9.0"):
        reasons.append(f"IELTS {ielts} must be between 4.0 and 9.0")
    if raw["duration_months"] and not (duration and 0 < duration <= 120):
        reasons.append(f"duration {raw['duration_months']!r} is not a valid number of months")
    if intakes is None:
        reasons.append(f"unrecognised intakes {raw['intakes']!r}")

    row = {
        "university_name": raw["university_name"],
        "university_slug": slugify(raw["university_name"]),
        "country": country,
        "city": raw["city"] or None,
        "website": raw["website"] or None,
        "title": raw["title"],
        "slug": slugify(raw["title"]),
        "level": level,
        "subject_area": raw["subject_area"],
        "duration_months": duration,
        "study_mode": study_mode,
        "intakes": intakes,
        "tuition_fee_international": fee,
        "currency": currency,
        "ielts_min": ielts,
        "source_url": raw["source_url"] or None,
    }
    if not reasons:
        row["content_hash"] = row_hash(row)
    return row, reasons


def clean(df: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """Split a DataFrame into valid cleaned rows and rejected raw rows.

    A row whose (university, title, level) already appeared earlier in the file
    is rejected as a duplicate. This catches exact duplicate rows and also rows
    that only differ in formatting, such as "£18,500" vs "18500".
    """
    valid, rejected = [], []
    first_seen = {}  # course key -> row number where it first appeared

    # Row numbers are 1-based data rows, matching what you see in a spreadsheet
    # below the header.
    for number, raw in enumerate(df.to_dict("records"), start=1):
        row, reasons = clean_row(raw)
        if not reasons:
            key = (row["university_slug"], row["slug"], row["level"])
            if key in first_seen:
                reasons = [f"duplicate of row {first_seen[key]}"]
            else:
                first_seen[key] = number
        if reasons:
            rejected.append({"row": number, **raw, "reason": "; ".join(reasons)})
        else:
            valid.append(row)
    return valid, rejected


def upsert_universities(rows: list[dict]) -> dict[str, University]:
    """Create or update each university in the file, keyed by slug."""
    rows_by_slug = defaultdict(list)
    for row in rows:
        rows_by_slug[row["university_slug"]].append(row)

    existing = db.session.scalars(select(University).where(University.slug.in_(rows_by_slug)))
    by_slug = {university.slug: university for university in existing}

    for slug, group in rows_by_slug.items():
        university = by_slug.get(slug)
        if university is None:
            university = University(slug=slug)
            db.session.add(university)
            by_slug[slug] = university
        # If a university is spelled several ways, keep its most common spelling.
        # Assigning an unchanged value is a no-op: SQLAlchemy only issues an
        # UPDATE for attributes whose value actually changed.
        university.name = Counter(row["university_name"] for row in group).most_common(1)[0][0]
        university.country = group[0]["country"]
        university.city = next((row["city"] for row in group if row["city"]), None)
        university.website = next((row["website"] for row in group if row["website"]), None)

    db.session.flush()  # sends the INSERTs so new universities get their ids
    return by_slug


def upsert_courses(rows: list[dict], universities: dict[str, University], run: IngestionRun):
    university_ids = [university.id for university in universities.values()]
    existing = db.session.scalars(select(Course).where(Course.university_id.in_(university_ids)))
    # One query for every course these universities already have, instead of
    # one lookup query per CSV row.
    by_key = {(course.university_id, course.slug, course.level): course for course in existing}

    now = utcnow()
    unchanged_ids = []
    for row in rows:
        university = universities[row["university_slug"]]
        course = by_key.get((university.id, row["slug"], row["level"]))

        if course is None:
            course = Course(university=university, slug=row["slug"], level=row["level"])
            db.session.add(course)
            run.inserted += 1
        elif course.content_hash != row["content_hash"]:
            run.updated += 1
        else:
            unchanged_ids.append(course.id)
            run.unchanged += 1
            continue

        for name in COURSE_FIELDS:
            setattr(course, name, row[name])
        course.content_hash = row["content_hash"]
        course.last_verified_at = now

    # Unchanged courses were still seen in the source, so mark them verified.
    # Setting updated_at to itself stops the onupdate hook from bumping it:
    # being re-verified is not a change to the course.
    if unchanged_ids:
        db.session.execute(
            update(Course)
            .where(Course.id.in_(unchanged_ids))
            .values(last_verified_at=now, updated_at=Course.updated_at)
        )


# A spreadsheet treats a cell starting with one of these as a formula.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def neutralise_formula(value):
    """Stop spreadsheet apps running report cells as formulas (CSV injection).

    The report echoes raw input back out, and people open it in Excel. A cell
    like =HYPERLINK("http://evil.example", "Click") would otherwise run. A
    leading apostrophe makes Excel and Sheets show the text as typed instead.
    """
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def write_report(rejected: list[dict], reports_dir: Path, started_at) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"rejected_{started_at:%Y%m%d_%H%M%S}.csv"
    safe_rows = [{key: neutralise_formula(value) for key, value in row.items()} for row in rejected]
    pd.DataFrame(safe_rows).to_csv(path, index=False)
    return path


def run_ingestion(csv_path: str | Path, reports_dir: str | Path) -> Result:
    """Ingest one CSV file. The upsert is a single transaction: either every
    valid row is saved or none are, and the run is recorded either way."""
    # Record the run first, in its own commit, so a crash still leaves a trace.
    run = IngestionRun(source_file=str(csv_path), status="running")
    db.session.add(run)
    db.session.commit()

    try:
        df = read_csv(Path(csv_path))
        valid, rejected = clean(df)
        run.rows_read = len(df)
        run.rejected = len(rejected)

        if valid:
            universities = upsert_universities(valid)
            upsert_courses(valid, universities, run)

        result = Result(run=run)
        if rejected:
            result.report_path = write_report(rejected, Path(reports_dir), run.started_at)

        run.status = "success"
        run.finished_at = utcnow()
        db.session.commit()
        return result
    except Exception:
        db.session.rollback()  # undo any half-finished upsert
        run.status = "failed"
        run.finished_at = utcnow()
        db.session.commit()
        raise
