"""Pydantic models: query parameters in, response bodies out.

Query models turn request.args (all strings) into typed, validated values and
raise ValidationError on bad input, which errors.py turns into a 400.
Response models decide exactly which fields leave the API, so adding a column
to a table never leaks it by accident.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    ValidationInfo,
    field_validator,
    model_validator,
)

from app.ingest.normalize import normalize_country, normalize_level, parse_intakes

# Timestamps are stored as naive UTC; send them with an explicit "Z" so clients
# don't have to guess the time zone.
UTCDateTime = Annotated[
    datetime,
    PlainSerializer(lambda value: value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")),
]

Country = Literal["UK", "CA"]
Level = Literal["Foundation", "Undergraduate", "Masters", "PhD"]


# ---------------------------------------------------------------- query params


class QueryParams(BaseModel):
    # Unknown parameters are an error, so a typo like ?contry=UK fails loudly
    # instead of silently returning unfiltered results.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    page: int = Field(1, ge=1)
    per_page: int = Field(20, ge=1, le=100)

    @model_validator(mode="before")
    @classmethod
    def drop_blank_values(cls, data):
        # A search form submits empty fields as "country=&level="; treat them as absent.
        return {key: value for key, value in data.items() if str(value).strip() != ""}

    @field_validator("country", mode="before", check_fields=False)
    @classmethod
    def accept_country_aliases(cls, value):
        # Reuse the ingestion normaliser, so "uk" and "Canada" work too.
        return normalize_country(value) or value


class UniversityQuery(QueryParams):
    country: Country | None = None


class CourseQuery(QueryParams):
    country: Country | None = None
    level: Level | None = None
    subject: str | None = Field(None, max_length=100)
    q: str | None = Field(None, max_length=100)
    max_fee: Decimal | None = Field(None, gt=0, max_digits=10, decimal_places=2)
    max_ielts: Decimal | None = Field(None, ge=0, le=9, max_digits=2, decimal_places=1)
    intake: str | None = None
    sort: Literal["title", "fee_asc", "fee_desc"] = "title"

    @field_validator("level", mode="before")
    @classmethod
    def accept_level_aliases(cls, value):
        return normalize_level(value) or value

    @field_validator("intake")
    @classmethod
    def canonical_month(cls, value):
        months = parse_intakes(value) if value else None
        if value is not None and (not months or len(months) != 1):
            raise ValueError("must be a single month name, e.g. September")
        return months[0] if months else None

    @field_validator("max_fee")
    @classmethod
    def fee_needs_country(cls, value, info: ValidationInfo):
        # UK fees are in GBP and Canadian fees in CAD, so "max_fee=20000" only
        # means something once we know which currency it is in. Fields validate
        # in declaration order, so country has already been checked here.
        if value is not None and info.data.get("country") is None:
            raise ValueError("needs country too, because UK fees are in GBP and Canadian in CAD")
        return value


# ------------------------------------------------------------------- responses


class OrmModel(BaseModel):
    # Lets model_validate() read attributes straight off SQLAlchemy objects.
    model_config = ConfigDict(from_attributes=True)


class UniversitySummary(OrmModel):
    name: str
    slug: str
    country: Country
    city: str | None


class UniversityOut(UniversitySummary):
    id: int
    website: str | None


class UniversityDetail(UniversityOut):
    course_count: int


class CourseOut(OrmModel):
    id: int
    title: str
    slug: str
    level: Level
    subject_area: str
    duration_months: int | None
    study_mode: str
    intakes: list[str]
    # Money is serialised as a string ("18500.00") so no client ever sees a
    # float rounding error.
    tuition_fee_international: Decimal
    currency: str
    ielts_min: Decimal | None
    source_url: str | None
    last_verified_at: UTCDateTime | None
    university: UniversitySummary


class CourseDetail(CourseOut):
    university: UniversityOut


class IngestionRunOut(OrmModel):
    id: int
    source_file: str
    status: str
    started_at: UTCDateTime
    finished_at: UTCDateTime | None
    rows_read: int
    inserted: int
    updated: int
    unchanged: int
    rejected: int
