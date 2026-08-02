"""Shared fixtures and helpers.

The browser modules each used to re-declare `served`, `_open` and the Playwright
skip preamble. Four copies of a fixture is how one of them ends up subtly
different - and `_server.start()` gained a `root=` parameter recently, which
would have meant chasing three call sites.
"""

import json
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


@pytest.fixture
def served_collision():
    """A server on the chrome-collision fixture - a page with content deliberately
    underneath the bar, the panel and the dock. Yields (tmp_dir, port)."""
    tmp, page = make_page("chrome-collision.html")
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


def centre(page, selector):
    """The viewport centre point of an element, as a click target."""
    return page.evaluate(
        """s => { const r = document.querySelector(s).getBoundingClientRect();
                  return {x: Math.round(r.left + r.width / 2),
                          y: Math.round(r.top + r.height / 2)}; }""",
        selector,
    )


def hit(page, selector):
    """Whether the Overlay or the page is on top at that element's centre.

    Not a consolidation of the elementFromPoint-at-centre copies elsewhere in the
    suite, though it was written as one and this docstring claimed to be. Those five -
    test_e2e_browser.py:1040, :1210, :1393 and test_e2e_shadow.py:161 - each ask about
    IDENTITY (`el.contains(hit)`, `t.id === 'hostile-bar'`, a class on the hit), which
    a chrome|page|none answer cannot express. They are still there because they cannot
    become this. Only one call site in the peek module is a genuine match.

    The drift the first version blamed does not exist either: for any positive-width
    DOMRect `x === left` by definition and both are viewport-relative, so `r.x` and
    `r.left` cannot disagree, scrolled or not.
    """
    p = centre(page, selector)
    return page.evaluate(
        """([x, y]) => { const e = document.elementFromPoint(x, y);
                         return e ? (e.closest('#wt-root') ? 'chrome' : 'page') : 'none'; }""",
        [p["x"], p["y"]],
    )


def click_el(page, selector):
    """Click where an element IS, rather than clicking the element.

    Playwright's own `page.click(selector)` scrolls the element into view and
    dispatches at its centre regardless of what is painted over it, which defeats the
    point of any test about the Overlay covering the page.
    """
    p = centre(page, selector)
    page.mouse.click(p["x"], p["y"])


def selected(page):
    """The tag of the current selection, or "" when nothing is selected.

    The empty-string case is the point: reading `#wt-seltag` directly cannot tell
    "nothing is selected" from "the tag is stale from the previous selection", so a
    regression that deselects instead of re-selecting reads as a pass. Every peek test
    turns on that distinction, which is why this lives here.

    Every equality read of the tag in the suite now goes through here - the browser,
    font-picker, spacing and change-list modules, and `select_card` below. The one
    remaining direct read is inside a JS `evaluate` block in test_e2e_browser.py, where
    a Python helper cannot reach.

    That conversion is worth its own note, because this docstring claimed it had
    happened for a while before it had, and the claim was the only evidence anyone had.
    """
    return page.evaluate(
        """() => { const b = document.getElementById('wt-selected');
                   return b.hidden ? '' :
                     document.getElementById('wt-seltag').textContent; }"""
    )


# The bar's worst case, assembled by hand because no single user action produces all
# of it at once: every control enabled, the longest status the Overlay writes, and the
# badge showing its longest text. The badge is the part that keeps being forgotten -
# it is hidden until a save, so an earlier version of the bar-fit test filtered it out
# with `!k.hidden` and passed while Save sat 65px off a 480px viewport the moment
# anything was saved. Whatever the bar can show at once is what has to fit.
#
# Here rather than in test_e2e_browser because the peek module measures the crumb in
# the same state. It used to import the JS from there under a private name, which is
# both a module reaching across into another module's internals and a 67KB import to
# fetch three constants.
LONGEST_STATUS = ("restored 4 of 6 edited elements; 2 could not be re-located"
                  " (kept for reconcile)")
LONGEST_BADGE = "source changed - reload"

WORST_CASE_BAR = """([status, badge]) => {
    document.getElementById('wt-status').textContent = status;
    const b = document.getElementById('wt-badge');
    b.hidden = false; b.textContent = badge; b.className = 'wt-badge wt-badge-warn';
    ['wt-undo', 'wt-redo', 'wt-reset-all', 'wt-deselect', 'wt-save']
        .forEach(id => { const e = document.getElementById(id); if (e) e.disabled = false; });
}"""


def worst_case_bar(page):
    """Drive the bar into the widest state it can render, all at once."""
    page.evaluate(WORST_CASE_BAR, [LONGEST_STATUS, LONGEST_BADGE])


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


def save(page, expect="saved"):
    """Click Save and wait for the write to land.

    `expect` is matched against the START of the status, not anywhere in it, and that
    is load-bearing: the batch-clearing message is "reverted - cleared saved edits",
    which CONTAINS "saved". Under a substring test every ordinary `save(page)` in the
    suite would be satisfied by a save that emitted no patches and wiped the pending
    batch - the failure would surface later as an opaque IndexError in whichever test
    happened to read patches()[0], or not at all.

    Pass expect="reverted" for the save that clears a session's last edit.
    """
    page.click("#wt-save")
    page.wait_for_function(
        "e => document.getElementById('wt-status').textContent.startsWith(e)",
        arg=expect,
    )


def patches(tmp, page="sample"):
    """The patches of the first batch in the edits file beside `page`."""
    doc = json.loads((tmp / f"{page}.webtweak.json").read_text())
    return doc["batches"][0]["patches"]


def changes(tmp, index=0):
    """One patch's recorded changes - the half of every assertion that says what
    Claude will receive, as opposed to what the page rendered."""
    return patches(tmp)[index]["changes"]


def place_shape(page, kind="square", x=400, y=350):
    """Open the palette, pick `kind`, and click the canvas at (x, y) to drop it."""
    page.click("#wt-shape-btn")
    page.click(f'.wt-shape-item[data-shape="{kind}"]')
    page.mouse.click(x, y)                     # place mode: next canvas click drops it
    page.wait_for_selector("svg.wt-shape")


def resize(page, width, height=900):
    """Resize the window and let the page actually observe it.

    `set_viewport_size` resolves before Chromium has necessarily dispatched the
    resize and media-query-change tasks, so reading the scope straight afterwards
    raced them and failed about one run in five. Waiting for `innerWidth` and then
    firing one more resize mirrors what a real drag does - it sends a stream of them,
    not a single event - rather than papering over the timing with a fixed pause.
    """
    page.set_viewport_size({"width": width, "height": height})
    page.wait_for_function("w => window.innerWidth === w", arg=width)
    page.evaluate("() => window.dispatchEvent(new Event('resize'))")


def pick(page, condition):
    """Choose a band in the Scope picker, the way a user does."""
    page.click("#wt-scope-toggle")
    page.click(f'#wt-scope-list .wt-band[data-condition="{condition}"]')


def rendered(page, selector, prop):
    """What the page actually renders - the only honest test of a preview."""
    return page.evaluate(
        "([s, p]) => getComputedStyle(document.querySelector(s)).getPropertyValue(p)",
        [selector, prop],
    )


def reload_and_restore(page):
    """Reload and wait for restore() to have finished re-applying this session."""
    page.reload()
    page.wait_for_selector("#wt-root")
    page.wait_for_function(
        "document.getElementById('wt-status').textContent.indexOf('restored') !== -1"
    )


def seed_batch(edits_file, session, patch_list, viewport=1280):
    """Write an edits file holding one pending batch for `session`."""
    edits_file.write_text(json.dumps({
        "target": "sample.html",
        "batches": [{"sessionId": session, "savedAt": "2026-01-01T00:00:00",
                     "viewport": viewport, "status": "pending", "patches": patch_list}],
    }))


def headline(page):
    """Select the fixture's h1.

    A helper exists here for an element only when clicking it needs care, which is
    the rule that keeps this file from growing one function per fixture element.
    The corner click is convention shared with select_card rather than a hazard of
    its own - `#headline` holds a bare text node, so its centre hits the h1 too -
    but it is the shape that stays correct if the heading ever gains a child.
    """
    page.click("#headline", position={"x": 8, "y": 8})


def select_card(page):
    """Select div.card itself, not one of its children.

    A plain page.click('.card') lands on the element's centre, which is over the
    card's <p>, so the overlay selects the paragraph and the test silently
    exercises the wrong element. The card has padding:24px, so clicking 8px in
    from its corner hits the card's own box. The assertion makes a mis-select
    fail loudly rather than quietly testing something else.
    """
    page.click(".card", position={"x": 8, "y": 8})
    assert selected(page) == "div.card"


def revert_shown(page, control):
    """Whether a control's revert dot is showing.

    Lived byte-identically in test_e2e_panel and test_e2e_banded_edits. Two copies is
    how one of them ends up subtly different, which is the reason this module's
    docstring gives for existing.
    """
    return page.eval_on_selector(f"#{control}-revert", "el => !el.hidden")
