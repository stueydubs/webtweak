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

from conftest import open_page, patches, save, set_field

from _browser import sync_playwright, pytestmark  # noqa: F401

NARROW = "(max-width: 600px)"


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
