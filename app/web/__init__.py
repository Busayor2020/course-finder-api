"""The search page at /. It is a plain HTML page whose JavaScript calls the
same JSON API that any other client would use."""

from flask import Blueprint, make_response, render_template

web = Blueprint("web", __name__)

# Only files from this site may load: no inline scripts, no third-party code.
# Even if course data somehow carried markup, the browser would refuse to run it.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; object-src 'none'; base-uri 'self'; "
    "form-action 'self'; frame-ancestors 'none'"
)


@web.get("/")
def index():
    response = make_response(render_template("index.html"))
    response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    return response
