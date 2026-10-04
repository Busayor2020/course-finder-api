from flask import request
from sqlalchemy import String, cast, or_, select
from sqlalchemy.orm import contains_eager, joinedload

from app.api import api_v1, paginated, single
from app.extensions import db
from app.models import Course, University
from app.schemas import CourseDetail, CourseOut, CourseQuery

SORTS = {
    "title": (Course.title.asc(),),
    "fee_asc": (Course.tuition_fee_international.asc(),),
    "fee_desc": (Course.tuition_fee_international.desc(),),
}


def like_pattern(text: str) -> str:
    """Escape LIKE wildcards so a search for "100%" matches the literal text."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@api_v1.get("/courses")
def list_courses():
    params = CourseQuery.model_validate(request.args.to_dict())

    # Join universities once: it serves the country filter, and contains_eager
    # fills course.university from that same join, so embedding the university
    # costs no extra queries (no N+1).
    query = select(Course).join(Course.university).options(contains_eager(Course.university))

    if params.country:
        query = query.where(University.country == params.country)
    if params.level:
        query = query.where(Course.level == params.level)
    if params.subject:
        query = query.where(Course.subject_area == params.subject)
    if params.q:
        pattern = like_pattern(params.q)
        query = query.where(
            or_(
                Course.title.ilike(pattern, escape="\\"),
                Course.subject_area.ilike(pattern, escape="\\"),
            )
        )
    if params.max_fee is not None:
        query = query.where(Course.tuition_fee_international <= params.max_fee)
    if params.max_ielts is not None:
        query = query.where(Course.ielts_min <= params.max_ielts)
    if params.intake:
        # intakes is a JSON list like ["January", "September"]. Matching the
        # quoted month in its text form works the same on MySQL and SQLite, and
        # the month was validated against a fixed list, so it can't over-match.
        query = query.where(cast(Course.intakes, String).like(f'%"{params.intake}"%'))

    # Course.id breaks ties, so rows with equal fees or titles keep a stable
    # order and pagination never shows a course twice or skips one.
    query = query.order_by(*SORTS[params.sort], Course.id)

    pagination = db.paginate(query, page=params.page, per_page=params.per_page, error_out=False)
    return paginated(pagination, CourseOut)


@api_v1.get("/courses/<int:course_id>")
def get_course(course_id):
    course = db.get_or_404(
        Course,
        course_id,
        options=[joinedload(Course.university)],
        description=f"No course with id {course_id}.",
    )
    return single(course, CourseDetail)
