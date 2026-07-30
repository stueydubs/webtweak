"""Browser end-to-end test of shape rotation.

Snapped to 45 degrees, not free. A decorative shape wants the eight orientations a
designer actually reaches for, and an arbitrary angle would be one more value to nudge
by eye when nothing else on the page sits at 37 degrees.

It also retires a palette entry: a square at 45 degrees IS the `diamond` that used to
be its own kind, which is the claim test_a_square_at_45_degrees_is_a_diamond checks
rather than assumes.
"""

from conftest import open_page, patches, place_shape, save, set_field

from _browser import sync_playwright, pytestmark  # noqa: F401


def box(page, selector="svg.wt-shape"):
    return page.evaluate(
        """s => { const r = document.querySelector(s).getBoundingClientRect();
                  return {w: Math.round(r.width), h: Math.round(r.height)}; }""",
        selector,
    )


def test_the_control_offers_only_45_degree_steps(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        place_shape(page)
        offered = page.evaluate(
            """() => Array.from(document.querySelectorAll('#wt-rot option'))
                .map(o => [o.value, o.textContent])"""
        )
        browser.close()
    assert [o[0] for o in offered] == ["0", "45", "90", "135", "180", "225", "270", "315"]
    # Shown in degrees, written as a bare number - a degree sign in the value would
    # only have to be parsed back off.
    assert [o[1] for o in offered][:2] == ["0°", "45°"]


def test_rotating_a_shape_previews_and_records_it(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        place_shape(page)
        set_field(page, "#wt-rot", "45")
        transform = page.eval_on_selector(
            "svg.wt-shape", "el => getComputedStyle(el).transform")
        save(page)
        browser.close()
    assert transform.startswith("matrix(0.707107")      # the page really is rotated
    assert patches(tmp)[0]["changes"]["transform"] == "rotate(45deg)"


def test_a_square_at_45_degrees_is_a_diamond(served):
    """The whole justification for retiring the `diamond` kind, asserted rather than
    asserted-in-a-comment: an 80px square turned 45 degrees occupies a box 80*sqrt(2)
    across, which is exactly the diamond it used to draw."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        place_shape(page, "square")
        before = box(page)
        set_field(page, "#wt-rot", "45")
        after = box(page)
        browser.close()
    assert before == {"w": 80, "h": 80}
    assert after == {"w": 113, "h": 113}                # 80 * sqrt(2), to the pixel


def test_the_panel_reads_back_the_angle_it_set(served):
    """Computed `transform` is always a matrix, so the angle has to be recovered from
    it - a control that cannot read its own value back shows 0 on every reselect."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        place_shape(page)
        set_field(page, "#wt-rot", "135")
        page.click("#wt-deselect")
        page.click("svg.wt-shape")
        shown = page.eval_on_selector("#wt-rot", "el => el.value")
        browser.close()
    assert shown == "135"


def test_turning_a_shape_back_to_its_original_angle_records_nothing(served):
    """The control speaks degrees while the property speaks `rotate(45deg)`, so the
    revert comparison has to happen in the control's terms - otherwise turning a shape
    back to square records a no-op declaration instead of dropping the edit."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        place_shape(page)
        set_field(page, "#wt-rot", "90")
        set_field(page, "#wt-rot", "0")
        save(page)
        browser.close()
    # The shape itself is still a create patch; what must be absent is any rotation.
    assert "transform" not in patches(tmp)[0]["changes"]


def test_undo_steps_back_through_a_rotation(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        place_shape(page)
        set_field(page, "#wt-rot", "90")
        page.click("#wt-undo")
        after = page.eval_on_selector(
            "svg.wt-shape", "el => getComputedStyle(el).transform")
        browser.close()
    assert after == "none"


def test_rotate_is_not_offered_for_ordinary_elements(served):
    """It lives in the Shape group, which hides for anything the Overlay did not
    create - a rotated paragraph is a layout decision, not a by-eye tweak."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        visible = page.eval_on_selector(
            '#wt-panel .wt-group[data-group="Shape"]', "el => !el.hidden")
        browser.close()
    assert visible is False
