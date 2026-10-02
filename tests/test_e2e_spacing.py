"""Browser end-to-end test of per-side margin and padding.

Margin and Padding were single text boxes holding a four-value shorthand, so
changing one side meant reading the shorthand, doing the arithmetic and retyping it.
Worse, the Patch carried all four sides whatever you touched - which is why the
reconcile skill has to warn that a computed `margin: 30px 168px 0 168px` may have
been an authored `margin: 30px auto 0`, and that reconciling it literally kills the
centring. Recording only the side that changed removes that hazard at the source, so
these tests assert on the Patch as much as on the render.
"""

from conftest import changes, open_page, save, select_card, selected, set_field

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
        assert selected(page) == "main.wrap"
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


def resolved_sides(recorded, prop="padding"):
    """What a reader of the Patch ends up with on each side: replay the changes in
    key order the way the stylesheet cascade (and rebuildInline) would, so a longhand
    that survives after the shorthand wins over it."""
    sides = {s: None for s in SIDES}
    for key, value in recorded.items():
        if key == prop:
            sides = {s: value for s in SIDES}
        elif key.startswith(prop + "-"):
            sides[key[len(prop) + 1:]] = value
    return [sides[s] for s in SIDES]


def test_a_linked_write_after_a_per_side_write_wins_after_a_rebuild(served):
    """Link 20px, unlink and set top 5px, link and set 30px. The preview shows 30px
    all round, but the map keeps the key order of FIRST insertion, so a replay put
    `padding-top: 5px` back after the shorthand and the top snapped back unprompted."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        page.click("#wt-padding-link")
        set_field(page, "#wt-padding-top", "20px")
        page.click("#wt-padding-link")
        set_field(page, "#wt-padding-top", "5px")
        page.click("#wt-padding-link")
        set_field(page, "#wt-padding-top", "30px")
        before = spacing_of(page, ".card", "padding")
        # Any rebuild of the element's inline style replays the whole map.
        set_field(page, "#wt-fs", "21px")
        after = spacing_of(page, ".card", "padding")
        page.keyboard.press("Control+z")
        page.keyboard.press("Control+y")
        redone = spacing_of(page, ".card", "padding")
        save(page)
        browser.close()
    assert before == ["30px"] * 4
    assert after == ["30px"] * 4          # the failure: top snapped back to 5px here
    assert redone == ["30px"] * 4
    recorded = changes(tmp)
    assert recorded["padding"] == "30px"
    assert "padding-top" not in recorded  # nothing survives to contradict the shorthand
    assert resolved_sides(recorded) == ["30px"] * 4


def test_a_per_side_write_after_a_linked_write_wins_after_a_rebuild(served):
    """The mirror: top first, then the shorthand, then top again. The map held top
    ahead of the shorthand, so a replay let the shorthand overwrite the later top edit.
    Top must stay at its last value through a rebuild, the other sides from the
    shorthand."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        set_field(page, "#wt-padding-top", "5px")
        page.click("#wt-padding-link")
        set_field(page, "#wt-padding-top", "30px")
        page.click("#wt-padding-link")
        set_field(page, "#wt-padding-top", "6px")      # top again, after the shorthand
        set_field(page, "#wt-fs", "21px")
        after = spacing_of(page, ".card", "padding")
        save(page)
        browser.close()
    assert after == ["6px", "30px", "30px", "30px"]
    assert resolved_sides(changes(tmp)) == ["6px", "30px", "30px", "30px"]


def test_undoing_a_linked_write_restores_the_per_side_edits_it_replaced(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        set_field(page, "#wt-padding-top", "5px")
        page.click("#wt-padding-link")
        set_field(page, "#wt-padding-top", "30px")
        set_field(page, "#wt-padding-top", "31px")     # typing: still one undo step
        linked = spacing_of(page, ".card", "padding")
        page.keyboard.press("Control+z")
        undone = spacing_of(page, ".card", "padding")
        browser.close()
    assert linked == ["31px"] * 4
    assert undone == ["5px", "24px", "24px", "24px"]


def test_a_linked_value_equal_to_the_top_baseline_is_not_a_revert(served):
    """Authored `padding: 10px 20px`: top's baseline is 10px but left and right are
    20px. Linked, typing 10px is a real request for 10px all round; comparing against
    the first box alone dropped it and snapped left and right back to 20px."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.add_style_tag(content=".card { padding: 10px 20px; }")
        select_card(page)
        start = boxes(page, "padding")
        page.click("#wt-padding-link")
        set_field(page, "#wt-padding-top", "10px")
        shown = boxes(page, "padding")
        rendered = spacing_of(page, ".card", "padding")
        save(page)
        browser.close()
    assert start == ["10px", "20px", "10px", "20px"]    # the fixture does differ per side
    assert shown == ["10px"] * 4
    assert rendered == ["10px"] * 4
    assert changes(tmp) == {"padding": "10px"}


def test_a_linked_value_equal_to_every_baseline_is_still_a_revert(served):
    """The all-four rule must not break the true revert: .card is 24px on every side,
    so linked 24px is putting it back and records nothing."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        page.click("#wt-padding-link")
        set_field(page, "#wt-padding-top", "40px")
        set_field(page, "#wt-padding-top", "24px")
        rendered = spacing_of(page, ".card", "padding")
        page.click("#wt-save")
        saved = page.eval_on_selector("#wt-status", "el => el.textContent")
        browser.close()
    assert rendered == ["24px"] * 4
    assert saved == "nothing changed yet"


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


# --- drag-to-scrub ----------------------------------------------------------
# Spacing is tuned by eye against the page rather than by typing a figure, so the
# boxes take a vertical drag: up adds, down subtracts, one CSS unit per pixel.

def scrub(page, field, dy, steps=8):
    """Drag a spacing box vertically. `dy` > 0 drags UP, which increases.

    Deliberately moves in several hops: a real drag is a stream of pointermoves,
    and the first implementation only worked for slow ones - it took the pointer
    capture at the 3px threshold rather than on pointerdown, so a quick flick left
    the 24px-tall box before any pointermove landed on it and nothing happened.
    """
    box = page.eval_on_selector(
        field, "el => { const b = el.getBoundingClientRect();"
               "return { x: b.x + b.width / 2, y: b.y + b.height / 2 }; }")
    page.mouse.move(box["x"], box["y"])
    page.mouse.down()
    for i in range(1, steps + 1):
        page.mouse.move(box["x"], box["y"] - dy * i / steps)
    page.mouse.up()


def test_dragging_a_spacing_box_up_increases_it(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        scrub(page, "#wt-padding-top", 20)
        field = page.input_value("#wt-padding-top")
        rendered = spacing_of(page, ".card", "padding")[0]
        browser.close()
    assert field == "44px"       # 24 + 20, unit preserved
    assert rendered == "44px"    # and the page actually shows it


def test_dragging_down_decreases_it(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        scrub(page, "#wt-padding-top", -10)
        rendered = spacing_of(page, ".card", "padding")[0]
        browser.close()
    assert rendered == "14px"


def test_a_fast_drag_scrubs_as_well_as_a_slow_one(served):
    """Two big jumps rather than eight small ones - the case the capture-on-threshold
    implementation silently ignored."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        scrub(page, "#wt-padding-top", 40, steps=2)
        rendered = spacing_of(page, ".card", "padding")[0]
        browser.close()
    assert rendered == "64px"


def test_a_whole_drag_is_one_undo_step(served):
    """A drag fires an input event per pointermove. Without the existing
    same-prop collapsing that would be dozens of undo steps for one gesture."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        scrub(page, "#wt-padding-top", 20)
        dragged = spacing_of(page, ".card", "padding")[0]
        page.keyboard.press("Control+z")
        undone = spacing_of(page, ".card", "padding")[0]
        browser.close()
    assert dragged == "44px"
    assert undone == "24px"


def test_dragging_padding_below_zero_stops_at_zero(served):
    """Padding cannot be negative, so the drag stops rather than recording a value
    the browser would discard."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        scrub(page, "#wt-padding-top", -200)
        field = page.input_value("#wt-padding-top")
        rendered = spacing_of(page, ".card", "padding")[0]
        browser.close()
    assert field == "0px"
    assert rendered == "0px"


def test_dragging_margin_below_zero_is_allowed(served):
    """A negative margin is a real technique - reconcile already maps an upward
    nudge onto one - so margin has no floor, unlike padding."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        scrub(page, "#wt-margin-top", -60)
        field = page.input_value("#wt-margin-top")
        browser.close()
    assert field == "-28px"      # 32 - 60


def test_a_plain_click_still_lands_a_caret_for_typing(served):
    """The drag must not swallow the click. Below the slop threshold nothing is
    scrubbed and the box behaves like the text input it is."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        page.click("#wt-padding-left")
        unchanged = page.input_value("#wt-padding-left")
        page.keyboard.press("Control+a")
        page.keyboard.type("9px")
        page.dispatch_event("#wt-padding-left", "input")
        typed = spacing_of(page, ".card", "padding")[3]
        browser.close()
    assert unchanged == "24px"
    assert typed == "9px"


def test_dragging_a_keyword_box_changes_nothing(served):
    """`auto` has no number to move. Turning it into one would invent a value the
    user never asked for - and silently kill a centred block."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        page.evaluate("document.getElementById('wt-margin-left').value = 'auto'")
        scrub(page, "#wt-margin-left", 25)
        field = page.input_value("#wt-margin-left")
        browser.close()
    assert field == "auto"
