"""Browser end-to-end test of banded edits surviving a reload (issue 0017).

A reload mid-session restores this session's pending edits, and that promise has to
keep holding now an edit carries a band. The failure this module exists to catch is
specific and silent: restoring a banded edit as *inline style* re-applies it at every
width, so a mobile-only change quietly becomes a change everywhere - and the page
gives the user no way to tell, because at the width they reloaded at it looks right.

So every test here asserts at two widths, for the same reason `test_e2e_banded_edits`
does: an edit checked only inside its band is indistinguishable from a flattened one.

`test_e2e_banded_edits` already covers this for a *hand-typed* band, where the bug
was found. These cover the mainline - a band the page itself declares - plus the two
behaviours that were written when a patch had one flat set of changes and needed
re-checking against the new shape: the unrelocatable-patch path and the
revert-to-baseline check.
"""

import json

from conftest import open_page, patches, save, set_field

from _browser import sync_playwright, pytestmark  # noqa: F401

NARROW = "(max-width: 600px)"
AUTHORED_NARROW = "32px"   # the fixture's own h1.title size inside NARROW
AUTHORED_BASE = "44px"     # ...and outside it


def resize(page, width):
    """Resize and let the page observe it (see test_e2e_breakpoints.resize)."""
    page.set_viewport_size({"width": width, "height": 900})
    page.wait_for_function("w => window.innerWidth === w", arg=width)
    page.evaluate("() => window.dispatchEvent(new Event('resize'))")


def pick(page, condition):
    page.click("#wt-scope-toggle")
    page.click(f'#wt-scope-list .wt-band[data-condition="{condition}"]')


def rendered(page, selector, prop):
    """What the page actually renders - the only honest test of a preview."""
    return page.evaluate(
        "([s, p]) => getComputedStyle(document.querySelector(s)).getPropertyValue(p)",
        [selector, prop],
    )


def headline(page):
    page.click("#headline", position={"x": 8, "y": 8})


def reload_and_restore(page):
    """Reload and wait for restore() to have finished re-applying."""
    page.reload()
    page.wait_for_selector("#wt-root")
    page.wait_for_function(
        "document.getElementById('wt-status').textContent.indexOf('restored') !== -1"
    )


def seed_batch(edits_file, session, patch_list):
    """Write an edits file holding one pending batch for `session`."""
    edits_file.write_text(json.dumps({
        "target": "sample.html",
        "batches": [{"sessionId": session, "savedAt": "2026-01-01T00:00:00",
                     "viewport": 480, "status": "pending", "patches": patch_list}],
    }))


def test_a_restored_banded_edit_still_applies_only_inside_its_band(served):
    """The module's whole reason to exist, on a band the page declares itself.

    The inline-style assertion names the failure mode directly: a restore that put
    the banded value on the element's style attribute would satisfy the inside-band
    read and fail only at the second width, and stating both makes the diagnosis
    obvious rather than leaving it to be inferred from a size mismatch.
    """
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        pick(page, NARROW)
        headline(page)
        set_field(page, "#wt-fs", "30px")
        save(page)

        reload_and_restore(page)
        inside = rendered(page, "#headline", "font-size")
        inline = page.eval_on_selector("#headline", "el => el.getAttribute('style') || ''")
        resize(page, 1280)
        outside = rendered(page, "#headline", "font-size")
        browser.close()

    assert inside == "30px"
    assert outside == AUTHORED_BASE, "restored as a base edit - it applies at every width"
    assert "font-size" not in inline, "the banded value was restored as inline style"


def test_an_element_with_both_a_base_and_a_banded_change_restores_both(served):
    """One element, one property, two recorded values - the release's silent failure,
    asserted across a reload. A restore that read only `changes` would drop the band;
    one that let the band overwrite the base would lose the wide value."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        pick(page, "")                       # base, at a narrow window, deliberately
        headline(page)
        set_field(page, "#wt-fs", "40px")
        pick(page, NARROW)
        set_field(page, "#wt-fs", "30px")
        save(page)

        reload_and_restore(page)
        narrow = rendered(page, "#headline", "font-size")
        resize(page, 1280)
        wide = rendered(page, "#headline", "font-size")
        browser.close()

    assert narrow == "30px"     # the band still wins where it applies...
    assert wide == "40px"       # ...and the base edit still governs everywhere else


def test_a_restored_banded_edit_re_saves_identically(served):
    """Restore reconstructs the entry a live edit would have built, so saving again
    without touching anything must write the same patch back - not a second patch for
    the same element, and not one that has drifted a value or lost its band."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        pick(page, NARROW)
        headline(page)
        set_field(page, "#wt-fs", "30px")
        save(page)
        first = patches(tmp)

        reload_and_restore(page)
        # A save with no further edits: the batch on disk is replaced by what the
        # restored session now holds, which is the round-trip under test.
        save(page)
        second = patches(tmp)
        browser.close()

    assert len(second) == 1, "the restored edit re-saved as more than one patch"
    assert second == first, "the patch drifted across the restore round-trip"


def test_an_unrelocatable_banded_patch_is_preserved_whole(served):
    """A patch whose element cannot be found is kept for reconcile rather than
    dropped. That promise predates bands, and the patch must come back with its
    `media` groups intact - a stranded patch reduced to its base changes would lose
    the responsive work silently, which is the same class of loss as flattening it."""
    tmp, port = served
    edits_file = tmp / "sample.webtweak.json"
    ghost = {
        "fingerprint": {"tag": "span", "id": "ghost", "classes": [], "text": "",
                        "ownText": "", "selector": "#ghost", "siblingIndex": 0,
                        "openTag": "<span id=\"ghost\">"},
        "changes": {"color": "#cc2222"},
        "media": {NARROW: {"font-size": "99px"}},
    }
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        session = page.evaluate("() => sessionStorage.getItem('wt-session-sample.html')")
        seed_batch(edits_file, session, [ghost])

        reload_and_restore(page)
        # A real edit on a locatable element, so the save has something of its own to
        # write - the stranded patch has to survive being re-emitted alongside it.
        pick(page, NARROW)
        headline(page)
        set_field(page, "#wt-fs", "30px")
        save(page)
        browser.close()

    saved = patches(tmp)
    kept = [q for q in saved if q["fingerprint"]["id"] == "ghost"]
    assert len(kept) == 1, "the stranded banded patch was dropped"
    assert kept[0] == ghost, "the stranded patch came back changed"


def test_reverting_a_restored_banded_edit_clears_the_batch(served):
    """The panel recovers a true authored baseline by reading computed style with the
    override peeled off - and with a band selected the override to peel is the
    injected rule, not the inline style. Set a restored banded edit back to the value
    the page's own media query authors and the batch must clear, exactly as the base
    case does. The fixture authors 32px inside this band and 44px outside it, so a
    peel that reached for the wrong override would compare against 44px and read a
    genuine revert as a fresh edit."""
    tmp, port = served
    edits_file = tmp / "sample.webtweak.json"
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        pick(page, NARROW)
        headline(page)
        set_field(page, "#wt-fs", "30px")
        save(page)
        assert len(json.loads(edits_file.read_text())["batches"]) == 1

        reload_and_restore(page)
        pick(page, NARROW)
        headline(page)
        set_field(page, "#wt-fs", AUTHORED_NARROW)   # back to what the page authors
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.indexOf('cleared') !== -1"
        )
        restored_size = rendered(page, "#headline", "font-size")
        browser.close()

    assert restored_size == AUTHORED_NARROW
    assert json.loads(edits_file.read_text())["batches"] == [], \
        "the revert left a no-op patch on disk"
