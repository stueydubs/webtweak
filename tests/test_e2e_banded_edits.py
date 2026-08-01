"""Browser end-to-end test of breakpoint-scoped preview and recording (issue 0015).

The release's centre. An edit made while a band is the editing target previews ONLY
in that band and records under that band's condition.

Every test here asserts at two widths, deliberately. The entire claim of the feature
is that the edit is conditional, so a banded edit checked at one width is not tested
at all - it is indistinguishable from a base edit that happens to look right.

The silent failure this module exists to catch: `font-size` at base and `font-size` at
`(max-width: 600px)` are two different recorded values on the same element and the
same property. Undo, the change list, the revert check and the unsaved flag all used
to assume one value per element per property, and a banded edit that quietly
overwrote a base one would still produce a valid-looking Patch.
"""

from conftest import (headline, open_page, patches, pick, place_shape, rendered,
                      resize, save, select_card, set_field)

from _browser import sync_playwright, pytestmark  # noqa: F401

NARROW = "(max-width: 600px)"


def revert_shown(page, control):
    return page.eval_on_selector(f"#{control}-revert", "el => !el.hidden")


def band_edit(page, value="30px", condition=NARROW):
    """Select the headline at a narrow window, target a band, and set a size."""
    pick(page, condition)
    headline(page)
    set_field(page, "#wt-fs", value)


def test_a_banded_edit_applies_inside_its_band_and_not_outside(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        band_edit(page)
        inside = rendered(page, "#headline", "font-size")
        resize(page, 1280)
        outside = rendered(page, "#headline", "font-size")
        browser.close()
    assert inside == "30px"
    # 44px is the fixture's authored base size. Not merely "not 30px": the edit has to
    # leave no trace outside its band, and a wrong-but-different value would pass a
    # weaker assertion.
    assert outside == "44px"


def test_a_banded_edit_records_under_its_condition_and_not_in_changes(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        band_edit(page)
        save(page)
        browser.close()
    patch = patches(tmp)[0]
    assert patch["media"][NARROW]["font-size"] == "30px"
    assert "font-size" not in patch.get("changes", {})


def test_a_base_edit_made_at_a_narrow_width_still_records_in_changes(served):
    """"This is wrong everywhere and I noticed it on mobile" has to stay expressible,
    and it is the window, not the scope, that would wrongly decide it."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        pick(page, "")                      # base, deliberately, at a narrow window
        headline(page)
        set_field(page, "#wt-fs", "30px")
        save(page)
        browser.close()
    patch = patches(tmp)[0]
    assert patch["changes"]["font-size"] == "30px"
    assert "media" not in patch


def test_the_same_property_at_base_and_in_a_band_keeps_both_values(served):
    """The release's silent failure, asserted directly: two values, one element, one
    property, neither overwriting the other."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        pick(page, "")
        headline(page)
        set_field(page, "#wt-fs", "40px")   # base
        pick(page, NARROW)
        set_field(page, "#wt-fs", "30px")   # ...and a different value in the band
        narrow = rendered(page, "#headline", "font-size")
        resize(page, 1280)
        wide = rendered(page, "#headline", "font-size")
        save(page)
        browser.close()
    assert narrow == "30px"          # the band wins where it applies...
    assert wide == "40px"            # ...and the base edit governs everywhere else
    patch = patches(tmp)[0]
    assert patch["changes"]["font-size"] == "40px"
    assert patch["media"][NARROW]["font-size"] == "30px"


def test_the_generated_preview_class_never_reaches_the_fingerprint(served):
    """An inline style cannot carry a media query, so the preview needs a class - and a
    class the Overlay invents must never become part of the page's captured identity."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        band_edit(page)
        on_element = page.eval_on_selector(
            "#headline", "el => Array.from(el.classList).filter(c => /^wt-mq-/.test(c))")
        save(page)
        browser.close()
    assert on_element, "the element should carry a generated preview class"
    fp = patches(tmp)[0]["fingerprint"]
    assert fp["classes"] == ["title"]
    for field in ("selector", "openTag"):
        assert "wt-mq-" not in fp[field]


def test_a_page_class_that_looks_generated_is_not_stripped(served):
    """`nonWtClasses` strips only the exact names the Overlay registered - a prefix
    match would erase a page's own design-system classes from its identity."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        page.evaluate("() => document.querySelector('#headline').classList.add('wt-mq-decoy')")
        band_edit(page)
        save(page)
        browser.close()
    assert "wt-mq-decoy" in patches(tmp)[0]["fingerprint"]["classes"]


def test_setting_a_banded_field_to_what_the_band_already_renders_records_nothing(served):
    """The band's own authored value is the baseline, not the base stylesheet's - the
    fixture renders the headline at 32px inside this band and 44px outside it."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        pick(page, NARROW)
        headline(page)
        shown = page.eval_on_selector("#wt-fs", "el => el.value")
        set_field(page, "#wt-fs", "32px")   # exactly what it already renders
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.length > 0")
        status = page.eval_on_selector("#wt-status", "el => el.textContent")
        browser.close()
    assert shown == "32px"
    assert status == "nothing changed yet"


def test_clearing_a_banded_field_reverts_only_that_band(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        pick(page, "")
        headline(page)
        set_field(page, "#wt-fs", "40px")
        pick(page, NARROW)
        set_field(page, "#wt-fs", "30px")
        set_field(page, "#wt-fs", "")       # abandon the banded edit
        narrow = rendered(page, "#headline", "font-size")
        save(page)
        browser.close()
    assert narrow == "40px"                 # back to the base edit, not to 32px
    patch = patches(tmp)[0]
    assert patch["changes"]["font-size"] == "40px"
    assert not patch.get("media", {}).get(NARROW, {})


def test_undo_steps_back_through_a_banded_edit_without_touching_the_base_one(served):
    """Undo is keyed by element and property, so this is where a banded edit would
    silently take a base one with it."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        pick(page, "")
        headline(page)
        set_field(page, "#wt-fs", "40px")
        pick(page, NARROW)
        set_field(page, "#wt-fs", "30px")
        page.click("#wt-undo")
        narrow = rendered(page, "#headline", "font-size")
        resize(page, 1280)
        wide = rendered(page, "#headline", "font-size")
        browser.close()
    assert narrow == "40px"     # the banded edit is gone...
    assert wide == "40px"       # ...and the base edit is untouched


def test_redo_puts_a_banded_edit_back(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        band_edit(page)
        page.click("#wt-undo")
        assert rendered(page, "#headline", "font-size") == "32px"
        page.click("#wt-redo")
        again = rendered(page, "#headline", "font-size")
        browser.close()
    assert again == "30px"


def test_the_change_list_distinguishes_a_banded_change_from_a_base_one(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        pick(page, "")
        headline(page)
        set_field(page, "#wt-fs", "40px")
        pick(page, NARROW)
        set_field(page, "#wt-fs", "30px")
        page.click("#wt-changes-head")      # open the list
        props = page.eval_on_selector("#wt-changes-list .wt-change-props",
                                      "el => el.textContent")
        browser.close()
    # Both are named, and the banded one says where it applies. A session spanning two
    # widths is otherwise a list of identical-looking rows.
    assert "font-size" in props
    assert "≤600px" in props


def test_reset_clears_a_banded_edit_too(served):
    """Reset discards the whole element, which now means its bands as well - otherwise
    a "reset" element keeps rendering a mobile-only override with nothing on screen
    saying so."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        band_edit(page)
        page.click("#wt-reset")
        after = rendered(page, "#headline", "font-size")
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.length > 0")
        status = page.eval_on_selector("#wt-status", "el => el.textContent")
        browser.close()
    assert after == "32px"                  # the fixture's own banded value
    assert status == "nothing changed yet"


def test_a_patch_carrying_no_band_is_unchanged_from_before(served):
    """The format change is additive: an edits file from a base-only session has to be
    byte-identical to what the previous release wrote, or every existing file becomes a
    migration problem."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=1280)
        headline(page)
        set_field(page, "#wt-fs", "48px")
        save(page)
        browser.close()
    patch = patches(tmp)[0]
    assert set(patch.keys()) == {"fingerprint", "changes"}
    assert patch["changes"] == {"font-size": "48px"}


def test_two_bands_on_one_element_stay_separate(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        pick(page, NARROW)
        headline(page)
        set_field(page, "#wt-fs", "30px")
        resize(page, 700)                   # out of the 600 band, into the 900
        pick(page, "(max-width: 900px)")
        set_field(page, "#wt-fs", "38px")
        mid = rendered(page, "#headline", "font-size")
        resize(page, 480)
        narrow = rendered(page, "#headline", "font-size")
        save(page)
        browser.close()
    assert mid == "38px"
    # Both bands match at 480px. The narrower one is declared later in the injected
    # block, so it wins - which is the same cascade rule the page's own CSS follows.
    assert narrow == "30px"
    media = patches(tmp)[0]["media"]
    assert media[NARROW]["font-size"] == "30px"
    assert media["(max-width: 900px)"]["font-size"] == "38px"


def test_two_different_elements_each_keep_their_own_banded_edit(served):
    """renderBandStyle()'s per-condition grouping is architected to hold more than one
    element's declarations under a shared band - every other test in this file only
    ever edits #headline, which cannot tell a correct per-element grouping apart from a
    bug that dropped or cross-leaked declarations between elements sharing a band."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        pick(page, NARROW)
        headline(page)
        set_field(page, "#wt-fs", "30px")
        page.click(".lede", position={"x": 8, "y": 8})   # scope survives selecting another element
        set_field(page, "#wt-fs", "15px")
        headline_narrow = rendered(page, "#headline", "font-size")
        lede_narrow = rendered(page, ".lede", "font-size")
        resize(page, 1280)
        headline_wide = rendered(page, "#headline", "font-size")
        lede_wide = rendered(page, ".lede", "font-size")
        save(page)
        browser.close()
    assert headline_narrow == "30px"
    assert lede_narrow == "15px"
    assert headline_wide == "44px"                        # base values, untouched
    assert lede_wide == "21px"
    ps = patches(tmp)
    assert len(ps) == 2
    headline_patch = next(p for p in ps if p["fingerprint"]["id"] == "headline")
    lede_patch = next(p for p in ps if p["fingerprint"]["id"] != "headline")
    assert headline_patch["media"][NARROW]["font-size"] == "30px"
    assert lede_patch["media"][NARROW]["font-size"] == "15px"
    assert "lede" in lede_patch["fingerprint"]["classes"]


def test_a_real_shapes_opentag_excludes_wt_shape(served):
    """openTag()'s Fingerprint-leak fix is documented as covering a shape's wt-shape
    class, but its only regression test drove a font-size band edit on #headline and
    never touched a real shape."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        place_shape(page)
        save(page)
        browser.close()
    create = next(p for p in patches(tmp) if p.get("op") == "create")
    fp = create["fingerprint"]
    assert "wt-shape" not in fp["classes"]
    # Not a bare substring check: the shape's OWN id is "wt-shape-<rand>" (a legitimate
    # attribute value, not a leak), so openTag has to be checked for the class token
    # specifically, not for "wt-shape" appearing anywhere in the tag at all.
    assert 'class="wt-shape"' not in fp["openTag"]


def test_status_message_never_pushes_save_off_screen(served):
    """Regression: a long status message ("reset - save to drop these edits") used to
    hold the bar at its own unwrapped width (.wt-status was flex-shrink:0, like every
    other bar control) and push Save past the viewport - at exactly the widths band
    editing exists to be used at. No earlier test did Reset-then-Save below 700px."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        headline(page)
        set_field(page, "#wt-fs", "30px")
        page.click("#wt-reset")
        box = page.eval_on_selector("#wt-save", "el => el.getBoundingClientRect()")
        # This used to time out: Save sat past the 480px viewport's right edge.
        page.click("#wt-save", timeout=5000)
        browser.close()
    assert box["right"] <= 480


def test_a_banded_edit_and_a_different_base_property_dont_cross_contaminate(served):
    """Every other base+band test in this file reuses font-size for both, which cannot
    distinguish correct per-key label/namespace handling from a bug that mismaps a
    band label or leaks a banded key into `changes`."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        pick(page, "")
        headline(page)
        set_field(page, "#wt-color", "#ff0000")    # base: a DIFFERENT property
        pick(page, NARROW)
        set_field(page, "#wt-fs", "30px")          # banded: font-size
        save(page)
        browser.close()
    patch = patches(tmp)[0]
    assert patch["changes"]["color"] == "#ff0000"
    assert "font-size" not in patch["changes"]
    assert patch["media"][NARROW] == {"font-size": "30px"}
    assert "color" not in patch["media"][NARROW]


def test_a_border_edit_under_a_band_still_lands_in_changes(served):
    """Regression: writeBorder() ends in the shared commit() tail, which used to read
    currentBand() unconditionally - a border edit made under a selected band was
    recorded into `media` even though border is documented (PRD, CHANGELOG) to stay
    base-only, and reconcile does not read `media` yet, so the edit was silently
    unreachable from real source."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        pick(page, NARROW)
        select_card(page)
        set_field(page, "#wt-bw", "5")
        save(page)
        browser.close()
    patch = patches(tmp)[0]
    assert "border" in patch["changes"]
    assert not patch.get("media", {})


def test_a_shape_edit_under_a_band_still_lands_in_changes(served):
    """Regression: a Shape-group control (Fill/Stroke/etc.) routed through the same
    shared commit() tail as any plain control, so a banded edit on a shape was
    recorded into `media` - then silently dropped altogether, because save()'s shape
    branch never read it at all."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        place_shape(page)
        pick(page, NARROW)
        set_field(page, "#wt-fill", "#00ff00")
        save(page)
        browser.close()
    create = next(p for p in patches(tmp) if p.get("op") == "create")
    assert create["changes"]["fill"] == "#00ff00"
    assert "media" not in create


def test_switching_scope_refreshes_the_revert_mark(served):
    """Regression: setScope() repopulated the shown VALUE for the new band but never
    refreshed the per-field revert-dot, so it kept reflecting whichever band was
    active before the switch until an unrelated edit happened to trigger a refresh."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        pick(page, "")
        headline(page)
        set_field(page, "#wt-fs", "40px")   # base override -> dot shows at Base
        assert revert_shown(page, "wt-fs") is True
        pick(page, NARROW)                  # no override recorded in this band yet
        shown = revert_shown(page, "wt-fs")
        browser.close()
    assert shown is False


def test_the_scope_note_declines_border_and_spacing_out_loud(served):
    """ADR-0004: "decline out loud rather than lie." Border and per-side spacing stay
    base-only regardless of the band shown - the scope note has to say so, or it
    reads as though the element's whole style applies at the band named there."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        pick(page, NARROW)
        select_card(page)
        note = page.eval_on_selector("#wt-scope-note", "el => el.textContent")
        browser.close()
    assert note.startswith("div.card at ")
    assert note.endswith(" - Border and spacing always apply at every width")


def test_the_scope_note_declines_shape_properties_out_loud(served):
    """Same principle, for a shape: every Shape-group control stays base-only too."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        place_shape(page)
        pick(page, NARROW)
        note = page.eval_on_selector("#wt-scope-note", "el => el.textContent")
        browser.close()
    assert note.endswith(" - Shape properties always apply at every width")


def offered_conditions(page):
    """Every condition the Scope picker currently offers."""
    page.click("#wt-scope-toggle")
    out = page.evaluate(
        """() => Array.from(document.querySelectorAll('#wt-scope-list .wt-band'))
            .map(b => b.dataset.condition)"""
    )
    page.click("#wt-scope-toggle")
    return out


def test_a_hand_typed_band_is_still_offered_after_a_reload(served):
    """`pageConditions()` re-derives itself from the page's stylesheets every call,
    so a band the CSS does not declare lives only in memory. restore() re-applied
    such an edit but never re-registered its condition, leaving the edit applying
    after a reload with its band gone from the picker - no way to return to it and
    revert it short of retyping the exact condition from memory.

    Asserts the edit too: a test that only read the list would pass against a
    restore that had dropped the edit entirely.
    """
    tmp, port = served
    typed = "(max-width: 520px)"   # deliberately not declared anywhere in the fixture
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        assert typed not in offered_conditions(page)
        page.fill("#wt-scope-input", typed)
        page.dispatch_event("#wt-scope-input", "change")
        select_card(page)
        set_field(page, "wt-fs", "31px")
        save(page)

        page.reload()
        page.wait_for_selector("#wt-scope-toggle")
        page.wait_for_function(
            "() => getComputedStyle(document.querySelector('.card')).fontSize === '31px'"
        )
        listed = offered_conditions(page)
        inside = rendered(page, ".card", "font-size")
        resize(page, 1280)
        outside = rendered(page, ".card", "font-size")
        browser.close()
    assert typed in listed, "the restored edit's band dropped out of the picker"
    assert inside == "31px"
    assert outside != "31px", "restored as a base edit - it applies at every width"
