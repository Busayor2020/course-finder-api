"""JSON error responses. Every error, from a bad query parameter to an unhandled
exception, comes back in the same envelope:

    {"error": {"code": "not_found", "message": "...", "details": {}}}
"""

from flask import Flask, current_app
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException


def error_response(status: int, code: str, message: str, details: dict | None = None):
    return {"error": {"code": code, "message": message, "details": details or {}}}, status


def handle_validation_error(error: ValidationError):
    # {"per_page": ["Input should be less than or equal to 100"]}
    details = {}
    for problem in error.errors(include_url=False):
        field = ".".join(str(part) for part in problem["loc"]) or "query"
        # Our own ValueErrors arrive as "Value error, <message>"; keep just the message.
        message = problem["msg"].removeprefix("Value error, ")
        details.setdefault(field, []).append(message)
    # A readable one-liner for UIs, e.g. "per_page: Input should be less than or equal to 100"
    message = "; ".join(f"{field}: {messages[0]}" for field, messages in details.items())
    return error_response(400, "invalid_parameters", message, details)


def handle_http_error(error: HTTPException):
    # Werkzeug's NotFound, MethodNotAllowed, etc.: "Not Found" -> "not_found"
    code = error.name.lower().replace(" ", "_")
    return error_response(error.code, code, error.description)


def handle_unexpected_error(error: Exception):
    # Log the full traceback, but never send internals to the client.
    current_app.logger.exception("Unhandled exception")
    return error_response(500, "internal_error", "Something went wrong on our side.")


def register_error_handlers(app: Flask) -> None:
    app.register_error_handler(ValidationError, handle_validation_error)
    app.register_error_handler(HTTPException, handle_http_error)
    app.register_error_handler(Exception, handle_unexpected_error)
