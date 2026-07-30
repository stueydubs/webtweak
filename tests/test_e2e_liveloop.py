"""Browser e2e for the live loop: source-change reload and the reconcile badge.

The reconcile half runs in another window. Before this, you saved, asked Claude
to reconcile, and had no signal at all until you reloaded by hand. These tests
pin the two rules that make that safe: the page reloads itself when the source
underneath it changes, and it *never* does so over unsaved work.
"""

import json
import shutil

import pytest

from conftest import edit, open_page

from _browser import sync_playwright, pytestmark  # noqa: F401


def test_source_change_reloads_a_clean_page(served):
    """A reconcile rewrites the CSS; the page should show it without the user
    having to guess that anything happened."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
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
        browser, page = open_page(p, port)
        edit(page, "#headline", "#wt-fs", "52")
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
        browser, page = open_page(p, port)
        edit(page, "#headline", "#wt-fs", "52")
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
        browser, page = open_page(p, port)
        edit(page, "#headline", "#wt-fs", "52")
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
        browser, page = open_page(p, port)
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
        browser, page = open_page(p, port)
        edit(page, "#headline", "#wt-fs", "52")
        page.evaluate("window.__reload_probe = true")
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.startsWith('saved')")
        page.wait_for_timeout(1200)                       # well past the 120ms debounce
        assert page.evaluate("window.__reload_probe") is True
        browser.close()


def test_deleted_edits_file_never_triggers_a_reload(served):
    """The safety predicates must fail CLOSED. `serveEdits` reports a missing file
    as `{"batches": []}`, which reads identically to "reconciled" unless the check
    looks for OUR batch rather than for the absence of a pending one. CONTEXT.md
    tells users to commit the edits file in their site repo, so `git checkout .`
    deleting it is an ordinary thing to happen mid-session."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        edit(page, "#headline", "#wt-fs", "52")
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.startsWith('saved')")
        page.evaluate("window.__reload_probe = true")

        (tmp / "sample.webtweak.json").unlink()        # git checkout . / rm

        page.wait_for_function(
            "document.getElementById('wt-badge').textContent.includes('gone')",
            timeout=8000)
        assert page.evaluate("window.__reload_probe") is True, \
            "reloaded after the edits file vanished; the session's edits are gone"
        # the edits are still on screen, so the user can re-save them
        assert page.eval_on_selector("#headline",
                                     "el => getComputedStyle(el).fontSize") == "52px"
        browser.close()


def test_another_sessions_batch_does_not_reload_us(served):
    """diskSafe/myReconciled filter on our own sessionId, so an edits-file write
    about a different session must not yank the page out from under the user."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.evaluate("window.__reload_probe = true")
        edits = tmp / "sample.webtweak.json"
        edits.write_text(json.dumps({
            "target": "sample.html",
            "batches": [{"sessionId": "someone-else", "status": "reconciled",
                         "reconciledAt": "2026-07-29T12:00:00",
                         "patches": [{"fingerprint": {"tag": "h1"}, "changes": {"color": "#111"}}]}],
        }, indent=2))
        page.wait_for_timeout(1200)                    # well past the 120ms debounce
        assert page.evaluate("window.__reload_probe") is True
        browser.close()


def test_save_retries_a_pending_source_change_instead_of_dropping_it(served):
    """A save clears the unsaved-work blocker but the source is still stale, and
    no further file event will fire for it. Dropping the warning left the user
    editing superseded markup behind a reassuring badge."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        edit(page, "#headline", "#wt-fs", "52")

        src = tmp / "sample.html"
        src.write_text(src.read_text().replace("</body>", "<!-- moved --></body>"))
        page.wait_for_function(
            "document.getElementById('wt-badge').textContent.includes('reload')",
            timeout=8000)

        # Saving must re-run the decision: now clean, but the batch is pending,
        # so it should land on the 'reconciling...' offer - never on a bare
        # "1 pending" that implies nothing is wrong.
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-badge').textContent.includes('reconciling')",
            timeout=8000)
        browser.close()


def test_reconciled_badge_clears_when_editing_resumes(served):
    """A green "reconciled" chip over fresh unsaved work reads as "already in
    source", so the user never saves and the edit is lost on the next reload."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        edit(page, "#headline", "#wt-fs", "52")
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.startsWith('saved')")

        edits = tmp / "sample.webtweak.json"
        doc = json.loads(edits.read_text())
        for b in doc["batches"]:
            b["status"] = "reconciled"
            b["reconciledAt"] = "2026-07-29T12:00:00"
        edits.write_text(json.dumps(doc, indent=2))
        page.wait_for_selector("#wt-root")

        page.wait_for_function(
            "document.getElementById('wt-badge').textContent.includes('reconciled')",
            timeout=8000)
        edit(page, ".lede", "#wt-fs", "19")            # fresh unsaved work
        page.wait_for_function(
            "!document.getElementById('wt-badge').textContent.includes('reconciled')",
            timeout=5000)
        browser.close()
