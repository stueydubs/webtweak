"""Shared fixtures and helpers.

The browser modules each used to re-declare `served`, `_open` and the Playwright
skip preamble. Four copies of a fixture is how one of them ends up subtly
different - and `_server.start()` gained a `root=` parameter recently, which
would have meant chasing three call sites.
"""

import shutil

import pytest

from _server import make_page, start, stop


@pytest.fixture
def served():
    """A webtweak server on an ephemeral port serving a fresh copy of the sample
    fixture. Yields (tmp_dir, port)."""
    tmp, page = make_page()
    proc, port = start(page)
    yield tmp, port
    stop(proc)
    shutil.rmtree(tmp, ignore_errors=True)


def open_page(playwright, port, name="sample.html", width=1280, height=900):
    """Launch Chromium on a served page with the overlay mounted.

    Returns (browser, page); the caller closes the browser.
    """
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={"width": width, "height": height})
    page.goto(f"http://127.0.0.1:{port}/{name}")
    page.wait_for_selector("#wt-root")
    return browser, page


def edit(page, selector, field, value):
    """Select an element and set one panel field, the way a user would."""
    page.click(selector)
    page.fill(field, value)
    page.dispatch_event(field, "input")


def set_field(page, field, value):
    """Set one panel field on the current selection, whatever kind of input it is.

    `page.fill` cannot drive a colour swatch or a select, and the panel now mixes
    all four kinds in one group, so every module needs this - assigning `.value`
    and dispatching `input` is exactly what the browser does for a real edit.
    """
    page.evaluate(
        """([id, v]) => {
            const el = document.getElementById(id);
            el.value = v;
            el.dispatchEvent(new Event('input', { bubbles: true }));
        }""",
        [field.lstrip("#"), value],
    )


def select_card(page):
    """Select div.card itself, not one of its children.

    A plain page.click('.card') lands on the element's centre, which is over the
    card's <p>, so the overlay selects the paragraph and the test silently
    exercises the wrong element. The card has padding:24px, so clicking 8px in
    from its corner hits the card's own box. The assertion makes a mis-select
    fail loudly rather than quietly testing something else.
    """
    page.click(".card", position={"x": 8, "y": 8})
    assert page.eval_on_selector("#wt-seltag", "el => el.textContent") == "div.card"
