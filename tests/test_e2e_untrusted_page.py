"""The overlay must be safe to point at a page you did not write.

webtweak's whole use case is opening local source from repos - including ones
you cloned. Every string the overlay renders about an element (tag, id, classes,
text) is attacker-controlled in that setting, and the overlay runs same-origin
with an endpoint that writes the file Claude later reconciles into real source.
So markup injected through an element name is not cosmetic: it is a path from
"inspect an untrusted page" to "attacker content written into your codebase".
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from _server import start, stop

pytest.importorskip(
    "playwright.sync_api",
    reason="install Playwright to run the browser e2e: "
           "pip install playwright && playwright install chromium",
)
from playwright.sync_api import sync_playwright  # noqa: E402

pytestmark = pytest.mark.browser  # selected by marker in CI, never by filename

# padding-top keeps the heading clear of the overlay's own top bar.
HOSTILE = (
    '<html><body style="padding-top:200px">\n'
    '<h1 id=\'a"><img src=x onerror=window.__PWNED=1>\'>Innocent heading</h1>\n'
    '<p class=\'b"><img src=y onerror=window.__PWNED_CLASS=1>\'>Body</p>\n'
    "</body></html>\n"
)


@pytest.fixture
def hostile():
    tmp = Path(tempfile.mkdtemp())
    page = tmp / "evil.html"
    page.write_text(HOSTILE, encoding="utf-8")
    proc, port = start(page)
    yield port
    stop(proc)
    shutil.rmtree(tmp, ignore_errors=True)


def test_element_id_cannot_execute_via_the_breadcrumb(hostile):
    """setCrumb used to build the breadcrumb with innerHTML, so selecting an
    element executed markup held in its id."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{hostile}/evil.html")
        page.wait_for_selector("#wt-root")
        page.click("h1")
        page.wait_for_timeout(300)
        assert page.evaluate("window.__PWNED") is None
        assert page.eval_on_selector_all("#wt-crumb img", "els => els.length") == 0
        # the name is still shown, just as text
        assert "img src=x" in page.eval_on_selector("#wt-crumb", "el => el.textContent")
        browser.close()


def test_element_class_cannot_execute_via_the_change_list(hostile):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{hostile}/evil.html")
        page.wait_for_selector("#wt-root")
        page.click("p")
        page.fill("#wt-fs", "19")
        page.dispatch_event("#wt-fs", "input")
        page.click("#wt-changes-head")
        page.wait_for_selector("#wt-changes-list:not([hidden])")
        page.wait_for_timeout(300)
        assert page.evaluate("window.__PWNED_CLASS") is None
        assert page.eval_on_selector_all("#wt-changes img", "els => els.length") == 0
        browser.close()


def test_hostile_names_survive_a_full_save(hostile):
    """The overlay must still function on such a page, not just refuse to run."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{hostile}/evil.html")
        page.wait_for_selector("#wt-root")
        page.click("h1")
        page.fill("#wt-fs", "52")
        page.dispatch_event("#wt-fs", "input")
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.startsWith('saved')")
        assert page.evaluate("window.__PWNED") is None
        browser.close()
