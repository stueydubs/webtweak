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

import pytest

from conftest import (open_page, patches, pick, reload_and_restore, rendered, resize,
                      save, seed_batch, set_field)

from _browser import sync_playwright, pytestmark  # noqa: F401

NARROW = "(max-width: 600px)"
AUTHORED_NARROW = "32px"   # the fixture's own h1.title size inside NARROW
AUTHORED_BASE = "44px"     # ...and outside it


# A fingerprint for the live `#headline` whose recorded ownText no longer matches, so
# restore() strands it while the element itself stays on the page and editable. Shared
# because three tests need exactly this shape and a drifted copy would quietly stop
# stranding - the patch would relocate, and the test would prove nothing.
STRANDED_HEADLINE_FP = {
    "tag": "h1", "id": "headline", "classes": ["title"], "text": "",
    "ownText": "some earlier wording", "selector": "#headline", "siblingIndex": 0,
    "openTag": '<h1 class="title" id="headline">',
}


def headline(page):
    page.click("#headline", position={"x": 8, "y": 8})


def previewed_conditions(page):
    """The conditions the injected preview stylesheet currently declares.

    Two widths cannot pin a band, only bracket it: a restore that re-registered a
    600px edit under `(max-width: 1100px)` passed every assertion in this module,
    because 480px and 1280px are both outside the band it got wrong. Reading the
    condition the Overlay actually wrote is cheaper than a third width and stronger
    than any number of them.
    """
    return page.evaluate(
        """() => {
            const el = document.getElementById('wt-band-style');
            return [...(el ? el.textContent : '').matchAll(/@media ([^{]+)\\{/g)]
                .map(m => m[1].trim());
        }"""
    )


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
        conditions = previewed_conditions(page)
        resize(page, 1280)
        outside = rendered(page, "#headline", "font-size")
        browser.close()

    assert inside == "30px"
    assert outside == AUTHORED_BASE, "restored as a base edit - it applies at every width"
    assert "font-size" not in inline, "the banded value was restored as inline style"
    assert conditions == [NARROW], f"restored under the wrong band: {conditions}"


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
    # Without this the round-trip claim is circular: an implementation that flattened
    # the band into `changes` at save time would satisfy `second == first` happily.
    assert first[0]["media"][NARROW]["font-size"] == "30px"
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


def test_a_stranded_banded_patch_survives_editing_the_same_element(served):
    """The harder half of "preserved whole": a patch can strand on an ownText mismatch
    while its element is still on the page and perfectly clickable - the source's copy
    changed, so the Overlay declines to assume it is the same element. If the user then
    edits that element, `save()` used to drop the stranded patch entirely, on the rule
    that a fresh patch supersedes it. That is true per declaration and false per patch:
    everything the fresh patch happened not to set went with it, silently, having just
    been reported as "kept for reconcile".

    The sibling test above uses `#ghost`, an id nothing on the page can ever match, so
    it exercises only the non-colliding path.
    """
    tmp, port = served
    edits_file = tmp / "sample.webtweak.json"
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        session = page.evaluate("() => sessionStorage.getItem('wt-session-sample.html')")
        # A real id, on an element that IS present - stranded only by the ownText guard.
        seed_batch(edits_file, session, [{
            "fingerprint": STRANDED_HEADLINE_FP,
            "changes": {"color": "#cc2222"},
            "media": {NARROW: {"letter-spacing": "2px"}},
        }])
        reload_and_restore(page)
        pick(page, NARROW)
        headline(page)
        set_field(page, "#wt-fs", "30px")     # the user edits that very element
        save(page)
        browser.close()

    patch = patches(tmp)[0]
    assert patch["changes"]["color"] == "#cc2222", "the stranded base change was lost"
    assert patch["media"][NARROW]["letter-spacing"] == "2px", \
        "the stranded banded change was lost"
    assert patch["media"][NARROW]["font-size"] == "30px"   # ...and the fresh edit is there


def test_a_fresh_edit_still_wins_over_a_stranded_one(served):
    """The other side of the same rule: carrying stranded declarations over must not
    resurrect a value the user has just re-authored. Fresh wins per declaration."""
    tmp, port = served
    edits_file = tmp / "sample.webtweak.json"
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        session = page.evaluate("() => sessionStorage.getItem('wt-session-sample.html')")
        seed_batch(edits_file, session, [{
            "fingerprint": STRANDED_HEADLINE_FP,
            "changes": {},
            "media": {NARROW: {"font-size": "99px"}},   # the SAME property, same band
        }])
        reload_and_restore(page)
        pick(page, NARROW)
        headline(page)
        set_field(page, "#wt-fs", "30px")
        save(page)
        browser.close()

    assert patches(tmp)[0]["media"][NARROW]["font-size"] == "30px", \
        "the stranded value overwrote the edit the user just made"


def test_merging_a_stranded_patch_does_not_pollute_the_session(served):
    """Carrying a stranded patch's declarations over must produce a new patch, not
    write them back into the live session entry.

    `save()` hands `e.changes` and each `e.media[cond]` straight into the patch it
    builds, so those maps are the session's own objects. Merging into them in place
    would leave the entry holding declarations that were never applied to the
    element - the change list would then name a property the page is not rendering,
    and the revert check would measure against a value that does not exist. The
    change list is where that surfaces, being the visible projection of that state.
    """
    tmp, port = served
    edits_file = tmp / "sample.webtweak.json"
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=1280)
        session = page.evaluate("() => sessionStorage.getItem('wt-session-sample.html')")
        seed_batch(edits_file, session, [{
            "fingerprint": STRANDED_HEADLINE_FP,
            "changes": {"letter-spacing": "3px"},
            "media": {},
        }])
        reload_and_restore(page)
        headline(page)
        set_field(page, "#wt-fs", "30px")
        save(page)
        page.click("#wt-changes-head")     # open the list, then force a repaint
        set_field(page, "#wt-fs", "31px")
        summary = page.eval_on_selector_all(
            "#wt-changes-list .wt-change-props", "els => els.map(e => e.textContent)"
        )
        browser.close()

    joined = " ".join(summary)
    assert "font-size" in joined, f"the list did not repaint as expected: {summary}"
    assert "letter-spacing" not in joined, (
        "the stranded patch's declarations were written into the live session entry: "
        + joined
    )


def test_reverting_a_restored_banded_edit_clears_the_batch(served):
    """The panel recovers a true authored baseline by reading computed style with the
    override peeled off - and with a band selected the override to peel is the
    injected rule, not the inline style. Set a restored banded edit back to the value
    the page's own media query authors and it must be recognised as a revert. The
    fixture authors 32px inside this band and 44px outside it, so a peel that reached
    for the wrong override would compare against 44px and read a genuine revert as a
    fresh edit."""
    tmp, port = served
    edits_file = tmp / "sample.webtweak.json"
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        pick(page, NARROW)
        headline(page)
        set_field(page, "#wt-fs", "30px")
        save(page)
        assert patches(tmp)[0]["media"][NARROW]["font-size"] == "30px"

        reload_and_restore(page)
        pick(page, NARROW)
        headline(page)
        set_field(page, "#wt-fs", AUTHORED_NARROW)   # back to what the page authors
        # Not save(): reverting the session's only edit reports "reverted - cleared
        # saved edits", which is the outcome under test and does not start with "saved".
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.indexOf('cleared') !== -1"
        )
        narrow = rendered(page, "#headline", "font-size")
        browser.close()

    assert narrow == AUTHORED_NARROW
    assert json.loads(edits_file.read_text())["batches"] == [], \
        "the revert left a no-op patch on disk"


@pytest.mark.parametrize(
    "typed,expect_band",
    [("40px", False),                 # back to what the band would render without it
     (AUTHORED_NARROW, True)],        # the page's authored value, but not the baseline
)
def test_a_bands_baseline_is_the_base_edit_not_the_pages_css(served, typed, expect_band):
    """Reverting a band has to peel that band's own override and nothing else.

    The single-edit revert test above cannot tell "peeled this band's baseline" from
    "peeled everything", because there is nothing else on the element to lose. The
    release keys every structure by (element, property, band) precisely so a base and
    a banded value can coexist, and a revert that reached too wide would take both
    while still looking correct at the width it was performed at.

    Which value counts as the revert is the interesting half, and it is easy to get
    backwards: NOT the fixture's authored 32px, but the base edit's 40px. A band's
    baseline is whatever would render at that width with the band's own override
    peeled off, and the user's own base edit is part of that - so 40px is a revert and
    32px is a real change. Both directions run through a reload, because the baseline
    has to be recovered from a restored entry, not just a live one.
    """
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        pick(page, "")
        headline(page)
        set_field(page, "#wt-fs", "40px")      # base
        pick(page, NARROW)
        set_field(page, "#wt-fs", "30px")      # ...and a different value in the band
        save(page)

        reload_and_restore(page)
        pick(page, NARROW)
        headline(page)
        set_field(page, "#wt-fs", typed)
        save(page)
        narrow = rendered(page, "#headline", "font-size")
        resize(page, 1280)
        wide = rendered(page, "#headline", "font-size")
        browser.close()

    patch = patches(tmp)[0]
    assert patch["changes"]["font-size"] == "40px", "the base edit was reverted too"
    assert wide == "40px", "the base edit stopped governing outside the band"
    if expect_band:
        assert patch["media"][NARROW]["font-size"] == typed, \
            "read as a revert against the page's CSS instead of against the base edit"
        assert narrow == typed
    else:
        assert "media" not in patch, "the band survived its own revert"
        assert narrow == "40px"   # the base edit governs here now, the band having gone
