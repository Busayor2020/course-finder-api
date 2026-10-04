from flask import request
from sqlalchemy import func, select

from app.api import api_v1, paginated, single
from app.extensions import db
from app.models import Course, University
from app.schemas import UniversityDetail, UniversityOut, UniversityQuery


@api_v1.get("/universities")
def list_universities():
    params = UniversityQuery.model_validate(request.args.to_dict())

    query = select(University).order_by(University.name, University.id)
    if params.country:
        query = query.where(University.country == params.country)

    pagination = db.paginate(query, page=params.page, per_page=params.per_page, error_out=False)
    return paginated(pagination, UniversityOut)


@api_v1.get("/universities/<slug>")
def get_university(slug):
    university = db.one_or_404(
        select(University).where(University.slug == slug),
        description=f"No university with slug {slug!r}.",
    )
    course_count = db.session.scalar(
        select(func.count(Course.id)).where(Course.university_id == university.id)
    )
    fields = UniversityOut.model_validate(university).model_dump()
    return single(UniversityDetail(**fields, course_count=course_count), UniversityDetail)
