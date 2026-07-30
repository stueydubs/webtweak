"""Browser end-to-end test of the Border group.

Width, Style and Colour are three controls over one `border` declaration, which is
the first time the panel's one-control-one-property assumption is bent (ADR-0003),
and the failure mode is silent: three controls overwriting each other's part of the
same declaration still produces a valid-looking Patch. So every test here asserts
both halves - what the page rendered AND what the Patch says - because the claim
being tested is that those two agree.
"""

from conftest import changes, open_page, place_shape, save, select_card, set_field

from _browser import sync_playwright, pytestmark  # noqa: F401

WIDTH, STYLE, COLOUR, RADIUS = "#wt-bw", "#wt-bs", "#wt-bc", "#wt-brad"
CARD_BORDER = "1px solid #e7e1d8"    # fixture .card, a uniform border
INK = "#1a1a1a"                      # fixture --ink, so also the default border colour


def border_of(page, selector):
    """What the page actually renders, side by side with what the panel claims."""
    return page.eval_on_selector(selector, """el => {
        const cs = getComputedStyle(el);
        return {width: cs.borderTopWidth, style: cs.borderTopStyle,
                colour: cs.borderTopColor, radius: cs.borderRadius};
    }""")


def fields(page):
    return page.evaluate(
        """() => ['wt-bw', 'wt-bs', 'wt-bc', 'wt-brad']
            .map(id => document.getElementById(id).value)"""
    )


def group_hidden(page, group="Border"):
    return page.eval_on_selector(
        f'#wt-panel .wt-group[data-group="{group}"]', "el => el.hidden")


def test_border_group_shows_for_elements_and_hides_for_shapes(served):
    """A CSS border on a shape's <svg> would draw a rectangle around a triangle, so
    the group hides for shapes exactly as typography and colour already do."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        on_element = group_hidden(page)
        present = page.evaluate(
            """() => ['wt-bw', 'wt-bs', 'wt-bc', 'wt-brad']
                .every(id => !!document.getElementById(id))"""
        )
        place_shape(page)
        on_shape = group_hidden(page)
        browser.close()
    assert present
    assert on_element is False
    assert on_shape is True


def test_colour_alone_renders_a_border_and_records_one_declaration(served):
    """The behaviour the whole design exists for: a colour on a border-less element
    is invisible on its own (the initial style is `none`), so touching it seeds the
    other two and a border appears. What records is the one thing that was on screen.
    """
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        set_field(page, COLOUR, "#ff0000")
        rendered = border_of(page, "#headline")
        shown = fields(page)
        save(page)
        browser.close()
    assert rendered["style"] == "solid"                  # seeded, and visible
    assert rendered["width"] == "1px"
    assert rendered["colour"] == "rgb(255, 0, 0)"
    assert shown[:3] == ["1", "solid", "#ff0000"]        # the panel shows the seeds
    assert changes(tmp) == {"border": "1px solid #ff0000"}   # ONE declaration


def test_width_alone_renders_a_border_and_records(served):
    """The other individually-invisible control. Its seeded colour needs no
    invention: computed border colour is the element's own text colour."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        set_field(page, WIDTH, "3")
        rendered = border_of(page, "#headline")
        save(page)
        browser.close()
    assert rendered["style"] == "solid"
    assert rendered["width"] == "3px"
    assert rendered["colour"] == "rgb(26, 26, 26)"       # --ink, via currentColor
    assert changes(tmp) == {"border": f"3px solid {INK}"}


def test_controls_populate_from_a_uniform_border(served):
    """An existing border is adjusted, not replaced from a default."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)                # .card { border: 1px solid #e7e1d8; radius 12px }
        shown = fields(page)
        browser.close()
    assert shown == ["1", "solid", "#e7e1d8", "12"]


def test_an_existing_border_is_adjusted_not_replaced(served):
    """Changing one part of a real border keeps the other two, so a recolour cannot
    silently reset the width or the style."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        set_field(page, COLOUR, "#0000ff")
        rendered = border_of(page, ".card")
        save(page)
        browser.close()
    assert rendered["width"] == "1px" and rendered["style"] == "solid"
    assert rendered["colour"] == "rgb(0, 0, 255)"
    assert changes(tmp)["border"] == "1px solid #0000ff"


def test_each_control_keeps_the_others_contribution(served):
    """The release's designated silent failure: three controls over one declaration
    can overwrite each other's part and still produce a valid-looking Patch. Set all
    three in turn and the last write must carry the first two, not a default.
    """
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        set_field(page, WIDTH, "6")
        set_field(page, STYLE, "dashed")
        set_field(page, COLOUR, "#00ff00")
        rendered = border_of(page, "#headline")
        save(page)
        browser.close()
    assert rendered == {"width": "6px", "style": "dashed",
                        "colour": "rgb(0, 255, 0)", "radius": "0px"}
    assert changes(tmp) == {"border": "6px dashed #00ff00"}


def test_style_none_removes_the_border_and_records(served):
    """`none` is expressible, and records as the canonical `border: none` rather
    than a width and colour beside a style that hides them."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        set_field(page, STYLE, "none")
        rendered = border_of(page, ".card")
        save(page)
        browser.close()
    assert rendered["style"] == "none" and rendered["width"] == "0px"
    assert changes(tmp) == {"border": "none"}


def test_clearing_a_border_field_reverts_the_whole_change(served):
    """The three controls share one property, so there is no partial border to keep.

    Width is the field a user can actually empty - a colour swatch and a select
    always hold a value - so it is the one the revert path has to handle.
    """
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        set_field(page, WIDTH, "6")
        widened = border_of(page, ".card")
        set_field(page, WIDTH, "")
        reverted = border_of(page, ".card")
        shown = fields(page)
        page.click("#wt-save")
        status = page.eval_on_selector("#wt-status", "el => el.textContent")
        browser.close()
    assert widened["width"] == "6px"
    assert reverted["width"] == "1px"                   # back to the authored border
    assert shown == ["1", "solid", "#e7e1d8", "12"]     # and so is the panel
    assert status == "nothing changed yet"


def test_undo_steps_back_through_a_border_change(served):
    """A composed declaration is one undo step like any other property."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        set_field(page, COLOUR, "#ff0000")
        page.keyboard.press("Control+z")
        rendered = border_of(page, "#headline")
        shown = fields(page)
        page.click("#wt-save")
        status = page.eval_on_selector("#wt-status", "el => el.textContent")
        browser.close()
    assert rendered["style"] == "none"                  # the border is gone again
    assert shown[:2] == ["0", "none"]                   # repopulated from the page
    assert status == "nothing changed yet"


def test_corner_radius_records(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        set_field(page, RADIUS, "24")
        rendered = border_of(page, ".card")
        save(page)
        browser.close()
    assert rendered["radius"] == "24px"
    assert changes(tmp) == {"border-radius": "24px"}


def test_radius_of_zero_records(served):
    """0 is meaningful here (sharp corners), as it is for a shape's radius - so the
    field must not floor at 1 the way font-size does."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        set_field(page, RADIUS, "0")
        rendered = border_of(page, ".card")
        save(page)
        browser.close()
    assert rendered["radius"] == "0px"
    assert changes(tmp) == {"border-radius": "0px"}


# --- per-side borders and the mixed-side guard (Issue 0010) -------------------
# A heading with a bottom rule must still be a heading with a bottom rule after you
# recolour it. Composing a four-sided border onto one would turn a divider into a
# box - a silent, destructive edit - so the controls target the single visible side,
# and decline entirely when several sides differ.


def all_sides(page, selector):
    return page.eval_on_selector(selector, """el => {
        const cs = getComputedStyle(el);
        return ['Top', 'Right', 'Bottom', 'Left'].map(
            s => cs['border' + s + 'Width'] + ' ' + cs['border' + s + 'Style']);
    }""")


def legend(page):
    return page.eval_on_selector(
        '#wt-panel .wt-group[data-group="Border"] .wt-legend', "el => el.textContent")


def disabled(page):
    return page.evaluate(
        """() => ['wt-bw', 'wt-bs', 'wt-bc', 'wt-brad']
            .map(id => document.getElementById(id).disabled)"""
    )


def test_a_one_sided_border_is_edited_on_that_side(served):
    """The controls populate from the bordered side and emit a per-side declaration,
    leaving the other three sides alone in the page AND in the Patch."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#ruled")             # .ruled { border-bottom: 2px solid var(--accent) }
        shown = fields(page)
        said = legend(page)
        set_field(page, COLOUR, "#0000ff")
        sides = all_sides(page, "#ruled")
        save(page)
        browser.close()
    assert shown[:3] == ["2", "solid", "#7a5c3e"]     # read off the bottom, not the top
    assert said == "Border (bottom)"                   # the side is named in the panel
    assert sides == ["0px none", "0px none", "2px solid", "0px none"]
    assert changes(tmp) == {"border-bottom": "2px solid #0000ff"}


def test_a_one_sided_border_keeps_its_width_when_only_the_style_changes(served):
    """Composition still holds per-side: the declaration carries all three parts."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#ruled")
        set_field(page, STYLE, "dashed")
        sides = all_sides(page, "#ruled")
        save(page)
        browser.close()
    assert sides == ["0px none", "0px none", "2px dashed", "0px none"]
    assert changes(tmp) == {"border-bottom": "2px dashed #7a5c3e"}


def test_mixed_sides_disable_the_border_controls(served):
    """Four sets of per-side controls would triple the densest part of the panel for
    an uncommon case, so the overlay declines and says why - rather than quietly
    replacing a deliberate design with a box."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#mixed-rule")
        state = disabled(page)
        said = legend(page)
        tip = page.eval_on_selector("#wt-bw", "el => el.title")
        browser.close()
    assert state == [True, True, True, False]   # the trio is off; radius still works
    assert said == "Border (sides differ)"
    assert "differ" in tip and tip != ""


def test_a_uniform_border_is_unaffected_by_the_side_logic(served):
    """The card and the headline keep the all-sides behaviour they had before."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        card_legend, card_state = legend(page), disabled(page)
        page.click("#headline")
        bare_legend, bare_state = legend(page), disabled(page)
        set_field(page, COLOUR, "#ff0000")
        sides = all_sides(page, "#headline")
        save(page)
        browser.close()
    assert card_legend == "Border" and card_state == [False] * 4
    assert bare_legend == "Border" and bare_state == [False] * 4
    assert sides == ["1px solid"] * 4                       # all four, as before
    assert changes(tmp) == {"border": "1px solid #ff0000"}


def test_undo_of_a_per_side_border_restores_the_rule(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#ruled")
        set_field(page, WIDTH, "8")
        widened = all_sides(page, "#ruled")
        page.keyboard.press("Control+z")
        restored = all_sides(page, "#ruled")
        page.click("#wt-save")
        status = page.eval_on_selector("#wt-status", "el => el.textContent")
        browser.close()
    assert widened == ["0px none", "0px none", "8px solid", "0px none"]
    assert restored == ["0px none", "0px none", "2px solid", "0px none"]
    assert status == "nothing changed yet"


def test_mixed_corner_radii_disable_the_radius_field(served):
    """Same principle as differing sides, one property along: a card rounded on its
    top two corners is a deliberate shape, and a single value here would round all
    four. The two guards are independent - this element has no border at all, so its
    Width/Style/Colour stay live while only Radius is declined.
    """
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#tab-top")               # .tab-top { border-radius: 12px 12px 0 0 }
        state = disabled(page)
        tip = page.eval_on_selector(RADIUS, "el => el.title")
        rendered = border_of(page, "#tab-top")
        browser.close()
    assert state == [False, False, False, True]   # only Radius is off
    assert "corner" in tip
    assert rendered["radius"] == "12px 12px 0px 0px"   # untouched, and untouchable


def test_shape_controls_read_stroke(served):
    """A shape's line is an SVG stroke, an element's is a CSS border - so the labels
    say so. The shape's Radius keeps its name: rx and border-radius are the same
    concept in the same units.
    """
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        place_shape(page)
        labels = page.evaluate(
            """() => ['wt-stroke', 'wt-sw', 'wt-rx'].map(
                id => document.getElementById(id).closest('.wt-field')
                        .querySelector('label').textContent)"""
        )
        browser.close()
    assert labels == ["Stroke", "Stroke width", "Radius"]
