"""Version 1 of the public API, mounted at /api/v1.

Like a Laravel route group with a prefix: every route registered on `api_v1`
gets the /api/v1 prefix. Putting the version in the URL lets a future v2 change
response shapes without breaking existing clients.
"""

from flask import Blueprint
from flask_sqlalchemy.pagination import Pagination
from pydantic import BaseModel

api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")


def paginated(pagination: Pagination, schema: type[BaseModel]) -> dict:
    """Success envelope for a list: {"data": [...], "meta": {...}}."""
    return {
        "data": [schema.model_validate(item).model_dump(mode="json") for item in pagination.items],
        "meta": {
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "pages": pagination.pages,
        },
    }


def single(item, schema: type[BaseModel]) -> dict:
    """Success envelope for one object: {"data": {...}}."""
    return {"data": schema.model_validate(item).model_dump(mode="json")}


# The route modules import `api_v1` from this file, so they are imported last,
# after it exists. Importing them is what registers their routes.
from app.api import courses, stats, universities  # noqa: E402, F401
