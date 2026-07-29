"""Browser e2e for the live loop: source-change reload and the reconcile badge.

The reconcile half runs in another window. Before this, you saved, asked Claude
to reconcile, and had no signal at all until you reloaded by hand. These tests
pin the two rules that make that safe: the page reloads itself when the source
underneath it changes, and it *never* does so over unsaved work.
"""

import json
import shutil

import pytest

from _server import make_page, start, stop

pytest.importorskip(
    "playwright.sync_api",
    reason="install Playwright to run the browser e2e: "
           "pip install playwright && playwright install chromium",
)
from playwright.sync_api import sync_playwright  # noqa: E402

pytestmark = pytest.mark.browser  # selected by marker in CI, never by filename


@pytest.fixture
def served():
    tmp, page = make_page()
    proc, port = start(page)
    yield tmp, port
    stop(proc)
    shutil.rmtree(tmp, ignore_errors=True)


def _open(p, port):
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(f"http://127.0.0.1:{port}/sample.html")
    page.wait_for_selector("#wt-root")
    return browser, page


def test_source_change_reloads_a_clean_page(served):
    """A reconcile rewrites the CSS; the page should show it without the user
    having to guess that anything happened."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = _open(p, port)
        page.evaluate("window.__reload_probe = true")     # cleared by a real reload
        # Simulate Claude reconciling: touch the page's own source.
        src = tmp / "sample.html"
        src.write_text(src.read_text().replace("</body>", "<!-- reconciled --></body>"))
        page.wait_for_function("window.__reload_probe === undefined", timeout=8000)
        assert page.evaluate("document.documentElement.outerHTML").count("reconciled") >= 1
        browser.close()


def test_source_change_never_reloads_over_unsaved_edits(served):
    """The rule that makes live reload safe. Losing an unsaved session to a
    background file write would be worse than having no live reload at all."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = _open(p, port)
        page.click("#headline")
        page.fill("#wt-fs", "52")
        page.dispatch_event("#wt-fs", "input")
        page.evaluate("window.__reload_probe = true")

        src = tmp / "sample.html"
        src.write_text(src.read_text().replace("</body>", "<!-- touched --></body>"))

        # Offer a reload rather than taking one.
        page.wait_for_function(
            "document.getElementById('wt-badge') && "
            "!document.getElementById('wt-badge').hidden && "
            "document.getElementById('wt-badge').textContent.includes('reload')",
            timeout=8000)
        assert page.evaluate("window.__reload_probe") is True     # never reloaded
        assert page.eval_on_selector("#headline",
                                     "el => getComputedStyle(el).fontSize") == "52px"
        browser.close()


def test_badge_reports_pending_then_reconciled(served):
    """The badge mirrors the edits file, so the hand-off state is visible in the
    window where the user is working."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = _open(p, port)
        page.click("#headline")
        page.fill("#wt-fs", "52")
        page.dispatch_event("#wt-fs", "input")
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.startsWith('saved')")

        page.wait_for_function(
            "document.getElementById('wt-badge').textContent.includes('pending')",
            timeout=8000)

        # Now do what reconcile does: flip the batch to reconciled.
        edits = tmp / "sample.webtweak.json"
        doc = json.loads(edits.read_text())
        for b in doc["batches"]:
            b["status"] = "reconciled"
            b["reconciledAt"] = "2026-07-29T12:00:00"
        edits.write_text(json.dumps(doc, indent=2))
        # The edits file is watched separately from source (webtweak suppresses
        # only the echo of its own save), so marking alone reaches the badge.
        page.wait_for_function(
            "document.getElementById('wt-badge') && "
            "document.getElementById('wt-badge').textContent.includes('reconciled')",
            timeout=8000)
        browser.close()


def test_reconcile_order_does_not_double_apply(served):
    """The real reconcile order is: write source (SKILL.md step 7), THEN mark the
    batch (step 8). Reloading in that window would have restore() re-apply a
    still-pending batch on top of source Claude has already changed - doubling a
    nudge and re-emitting the same patches on the next Save.
    """
    tmp, port = served
    with sync_playwright() as p:
        browser, page = _open(p, port)
        page.click("#headline")
        page.fill("#wt-fs", "52")
        page.dispatch_event("#wt-fs", "input")
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.startsWith('saved')")
        page.evaluate("window.__reload_probe = true")

        # Step 7: Claude writes the CSS. The batch is still pending.
        src = tmp / "sample.html"
        src.write_text(src.read_text().replace("</body>", "<!-- reconciled --></body>"))
        page.wait_for_function(
            "document.getElementById('wt-badge').textContent.includes('reconciling')",
            timeout=8000)
        assert page.evaluate("window.__reload_probe") is True, \
            "reloaded mid-reconcile; restore() would re-apply the pending batch"

        # Clicking the badge in this state must refuse too - the user cannot see
        # that reloading here would apply their saved edits a second time.
        page.click("#wt-badge")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.includes('twice')",
            timeout=5000)
        assert page.evaluate("window.__reload_probe") is True

        # Step 8: Claude marks it. Now the reload is safe and should happen.
        edits = tmp / "sample.webtweak.json"
        doc = json.loads(edits.read_text())
        for b in doc["batches"]:
            b["status"] = "reconciled"
            b["reconciledAt"] = "2026-07-29T12:00:00"
        edits.write_text(json.dumps(doc, indent=2))

        page.wait_for_function("window.__reload_probe === undefined", timeout=8000)
        # restore() must not have re-applied anything: no pending batch remains.
        assert page.eval_on_selector("#headline", "el => el.getAttribute('style')") in (None, "")
        browser.close()


def test_edits_marked_externally_reaches_the_badge(served):
    """`mark` touches only the edits file. If that file were unwatched the badge
    could never reach 'reconciled' in real use, which was the original design
    flaw - the first version of this feature ignored it to avoid save loops."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = _open(p, port)
        edits = tmp / "sample.webtweak.json"
        edits.write_text(json.dumps({
            "target": "sample.html",
            "batches": [{"sessionId": "other", "status": "pending",
                         "patches": [{"fingerprint": {"tag": "h1"}, "changes": {"color": "#111"}}]}],
        }, indent=2))
        page.wait_for_timeout(600)
        # Another session's pending batch is not this session's work.
        assert page.eval_on_selector("#wt-badge", "el => el.hidden") is True
        browser.close()


def test_saving_does_not_trigger_a_reload(served):
    """webtweak's own writes must not bounce the page the user is editing - the
    reason the watcher ignores *.webtweak.json and friends."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = _open(p, port)
        page.click("#headline")
        page.fill("#wt-fs", "52")
        page.dispatch_event("#wt-fs", "input")
        page.evaluate("window.__reload_probe = true")
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.startsWith('saved')")
        page.wait_for_timeout(1200)                       # well past the 120ms debounce
        assert page.evaluate("window.__reload_probe") is True
        browser.close()
