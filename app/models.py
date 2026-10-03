"""Database tables, declared as SQLAlchemy 2.0 typed models."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

COUNTRIES = ("UK", "CA")
LEVELS = ("Foundation", "Undergraduate", "Masters", "PhD")
STUDY_MODES = ("full_time", "part_time")
CURRENCIES = ("GBP", "CAD")
RUN_STATUSES = ("running", "success", "failed")


def utcnow() -> datetime:
    """Current UTC time without tzinfo. All timestamps are stored as naive UTC."""
    return datetime.now(UTC).replace(tzinfo=None)


def in_list(column: str, values: tuple[str, ...]) -> str:
    """SQL for a CHECK constraint limiting a column to a fixed set of values."""
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class University(TimestampMixin, db.Model):
    __tablename__ = "universities"
    __table_args__ = (CheckConstraint(in_list("country", COUNTRIES), name="country"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(200), unique=True)
    country: Mapped[str] = mapped_column(String(2), index=True)
    city: Mapped[str | None] = mapped_column(String(100))
    website: Mapped[str | None] = mapped_column(String(255))

    courses: Mapped[list[Course]] = relationship(back_populates="university")

    def __repr__(self) -> str:
        return f"<University {self.slug}>"


class Course(TimestampMixin, db.Model):
    __tablename__ = "courses"
    __table_args__ = (
        UniqueConstraint("university_id", "slug", "level"),
        CheckConstraint(in_list("level", LEVELS), name="level"),
        CheckConstraint(in_list("study_mode", STUDY_MODES), name="study_mode"),
        CheckConstraint(in_list("currency", CURRENCIES), name="currency"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    university_id: Mapped[int] = mapped_column(ForeignKey("universities.id"))
    title: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255))
    level: Mapped[str] = mapped_column(String(20), index=True)
    subject_area: Mapped[str] = mapped_column(String(100), index=True)
    duration_months: Mapped[int | None]
    study_mode: Mapped[str] = mapped_column(String(10), default="full_time")
    intakes: Mapped[list[str]] = mapped_column(JSON, default=list)
    tuition_fee_international: Mapped[Decimal] = mapped_column(Numeric(10, 2), index=True)
    currency: Mapped[str] = mapped_column(String(3))
    ielts_min: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))
    source_url: Mapped[str | None] = mapped_column(String(500))
    content_hash: Mapped[str] = mapped_column(CHAR(64))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime)

    university: Mapped[University] = relationship(back_populates="courses")

    def __repr__(self) -> str:
        return f"<Course {self.slug} ({self.level})>"


class IngestionRun(db.Model):
    __tablename__ = "ingestion_runs"
    __table_args__ = (CheckConstraint(in_list("status", RUN_STATUSES), name="status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_file: Mapped[str] = mapped_column(String(255))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    rows_read: Mapped[int] = mapped_column(default=0)
    inserted: Mapped[int] = mapped_column(default=0)
    updated: Mapped[int] = mapped_column(default=0)
    unchanged: Mapped[int] = mapped_column(default=0)
    rejected: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(20), default="running")

    def __repr__(self) -> str:
        return f"<IngestionRun {self.id} {self.status}>"
