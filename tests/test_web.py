from html.parser import HTMLParser


class FormControls(HTMLParser):
    """Collects form control ids and the ids that <label for="..."> points at."""

    def __init__(self):
        super().__init__()
        self.controls, self.labelled = set(), set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("input", "select", "textarea"):
            self.controls.add(attrs.get("id"))
        if tag == "label":
            self.labelled.add(attrs.get("for"))


def test_search_page_renders_the_form(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    html = response.get_data(as_text=True)
    assert '<form id="search-form"' in html
    assert 'src="/static/app.js"' in html
    assert "synthetic" in html


def test_every_form_control_has_a_visible_label(client):
    parser = FormControls()
    parser.feed(client.get("/").get_data(as_text=True))

    assert parser.controls == {"q", "country", "level", "intake", "max_fee", "sort"}
    assert parser.controls <= parser.labelled


def test_search_page_only_allows_its_own_scripts(client):
    policy = client.get("/").headers["Content-Security-Policy"]

    assert "default-src 'self'" in policy


def test_static_assets_are_served(client):
    for path in ("/static/app.js", "/static/styles.css"):
        assert client.get(path).status_code == 200


def test_page_script_never_uses_inner_html(client):
    # Course data must be written with textContent so it can never become markup.
    script = client.get("/static/app.js").get_data(as_text=True)

    for html_sink in (".innerHTML", ".outerHTML", "insertAdjacentHTML", "document.write"):
        assert html_sink not in script
