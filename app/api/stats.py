from datetime import timedelta

from sqlalchemy import func, or_, select

from app.api import api_v1
from app.extensions import db
from app.models import Course, IngestionRun, University, utcnow
from app.schemas import IngestionRunOut

STALE_AFTER = timedelta(days=30)


@api_v1.get("/stats")
def stats():
    by_country = db.session.execute(
        select(University.country, func.count(Course.id))
        .join(Course.university)
        .group_by(University.country)
        .order_by(University.country)
    ).all()
    by_level = db.session.execute(
        select(Course.level, func.count(Course.id)).group_by(Course.level).order_by(Course.level)
    ).all()
    latest_run = db.session.scalars(
        select(IngestionRun).order_by(IngestionRun.id.desc()).limit(1)
    ).first()
    stale = db.session.scalar(
        select(func.count(Course.id)).where(
            or_(
                Course.last_verified_at.is_(None),
                Course.last_verified_at < utcnow() - STALE_AFTER,
            )
        )
    )

    return {
        "data": {
            "total_courses": sum(count for _, count in by_country),
            "courses_by_country": dict(by_country),
            "courses_by_level": dict(by_level),
            "stale_courses": stale,
            "stale_after_days": STALE_AFTER.days,
            "latest_ingestion": (
                IngestionRunOut.model_validate(latest_run).model_dump(mode="json")
                if latest_run
                else None
            ),
        }
    }
