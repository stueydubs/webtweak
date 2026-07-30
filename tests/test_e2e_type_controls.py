"""Browser end-to-end test of the Line stepper and the Spacing presets.

Both were bare text boxes you typed a value into from memory. Both keep accepting
free text - `normal`, an em, a px - because a stepper that only handled unitless
numbers, or a closed dropdown of presets, would each remove an edit that works
today. So the tests here come in pairs: the new affordance, and the typed value it
must not have replaced.
"""

from conftest import changes, open_page, save, set_field

from _browser import sync_playwright, pytestmark  # noqa: F401

LINE, UP, DOWN = "#wt-lh", "#wt-lh-up", "#wt-lh-down"
SPACING, SPACING_TOGGLE, SPACING_LIST = "#wt-ls", "#wt-ls-toggle", "#wt-ls-list"


def line_of(page, selector):
    return page.eval_on_selector(selector, """el => {
        const cs = getComputedStyle(el);
        return +(parseFloat(cs.lineHeight) / parseFloat(cs.fontSize)).toFixed(2);
    }""")


def test_the_line_field_steps_up_and_down(served):
    """.lede is line-height 1.6 by inheritance from body."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click(".lede")
        page.click(UP)
        after_up = page.eval_on_selector(LINE, "el => el.value")
        rendered = line_of(page, ".lede")
        page.click(DOWN)
        page.click(DOWN)
        after_down = page.eval_on_selector(LINE, "el => el.value")
        save(page)
        browser.close()
    assert after_up == "1.7"
    assert rendered == 1.7                  # stepped on the page, not just in the field
    assert after_down == "1.5"
    assert changes(tmp) == {"line-height": "1.5"}


def test_stepping_a_line_height_of_normal_resolves_it_first(served):
    """A number input could not hold `normal` at all. The stepper resolves it to the
    ratio the browser is already rendering, then steps that - so the first press does
    something sensible instead of nothing."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        set_field(page, LINE, "normal")
        page.click(UP)
        shown = page.eval_on_selector(LINE, "el => el.value")
        save(page)
        browser.close()
    stepped = float(shown)
    assert 1.0 < stepped < 1.5              # normal is ~1.1-1.2, plus one step
    assert changes(tmp)["line-height"] == shown


def test_stepping_keeps_the_unit_it_was_given(served):
    """`line-height: 1.4em` is a real thing to author, so a step must not silently
    strip the unit and change what the value means."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        set_field(page, LINE, "1.4em")
        page.click(UP)
        shown = page.eval_on_selector(LINE, "el => el.value")
        save(page)
        browser.close()
    assert shown == "1.5em"
    assert changes(tmp) == {"line-height": "1.5em"}


def test_a_typed_line_height_still_works(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click(".lede")
        set_field(page, LINE, "2.25")
        save(page)
        browser.close()
    assert changes(tmp) == {"line-height": "2.25"}


def test_the_line_stepper_will_not_step_below_zero(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click(".lede")
        set_field(page, LINE, "0.1")
        page.click(DOWN)
        page.click(DOWN)
        shown = page.eval_on_selector(LINE, "el => el.value")
        browser.close()
    assert float(shown) >= 0


def test_spacing_offers_presets_including_normal(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click(".eyebrow")
        page.click(SPACING_TOGGLE)
        entries = page.eval_on_selector_all(
            f"{SPACING_LIST} .wt-suggest-item", "els => els.map(e => e.dataset.value)")
        browser.close()
    assert "normal" in entries                       # the one that removes tracking
    assert any(e.startswith("-") for e in entries)   # and one that tightens
    assert len(entries) >= 5


def test_picking_a_spacing_preset_applies_and_records(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        page.click(SPACING_TOGGLE)
        page.click(f"{SPACING_LIST} .wt-suggest-item[data-value='0.08em']")
        rendered = page.eval_on_selector(
            "#headline", "el => getComputedStyle(el).letterSpacing")
        save(page)
        browser.close()
    assert rendered != "normal"
    assert changes(tmp) == {"letter-spacing": "0.08em"}


def test_a_typed_spacing_still_works(served):
    """The presets are a shortcut, not a cage."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        set_field(page, SPACING, "0.3px")
        save(page)
        browser.close()
    assert changes(tmp) == {"letter-spacing": "0.3px"}
