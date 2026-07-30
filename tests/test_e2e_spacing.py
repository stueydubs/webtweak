"""Browser end-to-end test of per-side margin and padding.

Margin and Padding were single text boxes holding a four-value shorthand, so
changing one side meant reading the shorthand, doing the arithmetic and retyping it.
Worse, the Patch carried all four sides whatever you touched - which is why the
reconcile skill has to warn that a computed `margin: 30px 168px 0 168px` may have
been an authored `margin: 30px auto 0`, and that reconciling it literally kills the
centring. Recording only the side that changed removes that hazard at the source, so
these tests assert on the Patch as much as on the render.
"""

from conftest import changes, open_page, save, select_card, set_field

from _browser import sync_playwright, pytestmark  # noqa: F401

SIDES = ("top", "right", "bottom", "left")


def boxes(page, prop="margin"):
    return page.evaluate(
        """prop => ['top','right','bottom','left']
            .map(s => document.getElementById('wt-' + prop + '-' + s).value)""",
        prop,
    )


def spacing_of(page, selector, prop="margin"):
    return page.evaluate(
        """([sel, prop]) => {
            const cs = getComputedStyle(document.querySelector(sel));
            return ['Top','Right','Bottom','Left'].map(s => cs[prop + s]);
        }""",
        [selector, prop],
    )


def test_each_side_populates_from_its_own_computed_value(served):
    """.card is margin 32px 0, padding 24px - so the boxes must differ per side
    rather than all showing one shorthand string."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        margins = boxes(page, "margin")
        paddings = boxes(page, "padding")
        browser.close()
    assert margins == ["32px", "0px", "32px", "0px"]
    assert paddings == ["24px", "24px", "24px", "24px"]


def test_editing_one_side_records_only_that_side(served):
    """The point of the whole change: the Patch says what changed, not all four."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        set_field(page, "#wt-padding-bottom", "40px")
        rendered = spacing_of(page, ".card", "padding")
        save(page)
        browser.close()
    assert rendered == ["24px", "24px", "40px", "24px"]     # only the bottom moved
    assert changes(tmp) == {"padding-bottom": "40px"}       # and only the bottom recorded


def test_a_centred_block_keeps_its_auto_margins(served):
    """The hazard this removes. main.wrap is `margin: 0 auto`; nudging its top margin
    used to send a four-value shorthand with the computed px where `auto` had been,
    and reconciling that literally would have killed the centring."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        # inside .wrap's own padding, but below the overlay's fixed 44px top bar,
        # which otherwise intercepts the click
        page.click(".wrap", position={"x": 6, "y": 60})
        assert page.eval_on_selector("#wt-seltag", "el => el.textContent") == "main.wrap"
        shown = boxes(page, "margin")
        set_field(page, "#wt-margin-top", "48px")
        save(page)
        browser.close()
    assert shown[1] != "0px" and shown[3] != "0px"   # auto resolves to real px here
    assert changes(tmp) == {"margin-top": "48px"}    # the auto sides are never mentioned


def test_auto_is_expressible_per_side(served):
    """A side box takes any length or `auto`, so centring becomes something you can
    author in the panel rather than only lose."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        set_field(page, "#wt-margin-left", "auto")
        set_field(page, "#wt-margin-right", "auto")
        save(page)
        browser.close()
    assert changes(tmp) == {"margin-left": "auto", "margin-right": "auto"}


def test_a_unit_other_than_px_is_expressible(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        set_field(page, "#wt-padding-top", "2rem")
        rendered = spacing_of(page, ".card", "padding")
        save(page)
        browser.close()
    assert rendered[0] == "32px"                       # 2rem against a 16px root
    assert changes(tmp) == {"padding-top": "2rem"}     # recorded as authored


def test_the_link_toggle_writes_all_four_as_a_shorthand(served):
    """"Same on all sides" was what the single box gave you, so it stays one action -
    and it records the shorthand, because that is what the user expressed."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        page.click("#wt-padding-link")
        set_field(page, "#wt-padding-top", "12px")
        shown = boxes(page, "padding")
        rendered = spacing_of(page, ".card", "padding")
        save(page)
        browser.close()
    assert shown == ["12px"] * 4                       # every box follows
    assert rendered == ["12px"] * 4
    assert changes(tmp) == {"padding": "12px"}


def test_clearing_one_side_reverts_only_that_side(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        set_field(page, "#wt-padding-top", "40px")
        set_field(page, "#wt-padding-left", "8px")
        set_field(page, "#wt-padding-top", "")
        rendered = spacing_of(page, ".card", "padding")
        save(page)
        browser.close()
    assert rendered == ["24px", "24px", "24px", "8px"]   # top back to authored
    assert changes(tmp) == {"padding-left": "8px"}


def test_an_invalid_side_value_records_nothing(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        set_field(page, "#wt-margin-top", "banana")
        status = page.eval_on_selector("#wt-status", "el => el.textContent")
        rendered = spacing_of(page, ".card", "margin")
        page.click("#wt-save")
        saved = page.eval_on_selector("#wt-status", "el => el.textContent")
        browser.close()
    assert status.startswith("ignored invalid margin-top")
    assert rendered[0] == "32px"
    assert saved == "nothing changed yet"


def test_undo_steps_back_through_one_side(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        set_field(page, "#wt-padding-right", "48px")
        widened = spacing_of(page, ".card", "padding")
        page.keyboard.press("Control+z")
        restored = spacing_of(page, ".card", "padding")
        browser.close()
    assert widened[1] == "48px"
    assert restored == ["24px"] * 4
