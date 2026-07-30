"""Browser end-to-end test of drag-to-draw shape placement.

Picking a shape and then pressing and dragging on the page used to do nothing visible
until the mouse came back up, at which point the shape appeared at a fixed default
size wherever the release happened. Both halves of that read as broken: nothing tracks
the pointer, and the size you were implicitly drawing is discarded.

Every drawing tool sizes the shape as you drag, so this makes webtweak do the same -
without losing click-to-place, which is still the fastest way to drop a default shape.
"""

from conftest import open_page, patches, save

from _browser import sync_playwright, pytestmark  # noqa: F401


def arm(page, kind="rectangle"):
    """Open the palette and pick a shape, leaving the Overlay in place mode."""
    page.click("#wt-shape-btn")
    page.click(f'.wt-shape-item[data-shape="{kind}"]')


def shape_box(page):
    """The drawn shape's own recorded geometry, as the panel and the patch see it."""
    return page.evaluate(
        """() => {
            const el = document.querySelector('svg.wt-shape');
            if (!el) return null;
            return {left: el.style.left, top: el.style.top,
                    width: el.style.width, height: el.style.height};
        }"""
    )


def test_the_shape_appears_and_tracks_the_pointer_during_the_drag(served):
    """The reported bug, asserted mid-gesture: the shape has to exist and be the size
    of the rectangle drawn SO FAR, before the button comes back up."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        arm(page)
        page.mouse.move(400, 300)
        page.mouse.down()
        page.mouse.move(500, 380)
        during = shape_box(page)          # still mid-drag: button is down
        page.mouse.move(560, 420)
        later = shape_box(page)
        page.mouse.up()
        browser.close()
    assert during is not None, "the shape should be on the page before the mouse is released"
    assert during["width"] == "100px" and during["height"] == "80px"
    # ...and it keeps following, rather than snapping once at the start.
    assert later["width"] == "160px" and later["height"] == "120px"


def test_the_drawn_shape_keeps_the_size_it_was_dragged_to(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        arm(page)
        page.mouse.move(400, 300)
        page.mouse.down()
        page.mouse.move(560, 420)
        page.mouse.up()
        box = shape_box(page)
        selected = page.eval_on_selector("#wt-seltag", "el => el.textContent")
        browser.close()
    assert box == {"left": "400px", "top": "300px", "width": "160px", "height": "120px"}
    assert selected.startswith("svg#wt-shape-")   # drawn, then selected to style


def test_drawing_up_and_to_the_left_works(served):
    """A drag is a rectangle between two corners, not a vector from an origin - so the
    press point can be any corner of it."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        arm(page)
        page.mouse.move(600, 460)
        page.mouse.down()
        page.mouse.move(440, 340)         # back up and to the left
        page.mouse.up()
        box = shape_box(page)
        browser.close()
    assert box == {"left": "440px", "top": "340px", "width": "160px", "height": "120px"}


def test_a_plain_click_still_drops_the_default_size(served):
    """Click-to-place is the fastest way to drop a shape you intend to size in the
    panel, so drawing must not cost it. A click is a drag of zero length, and a shape
    of zero size would be worse than useless."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, )
        arm(page, "square")
        page.mouse.click(420, 360)
        box = shape_box(page)
        browser.close()
    # The square's declared default, placed at the click point.
    assert box == {"left": "420px", "top": "360px", "width": "80px", "height": "80px"}


def test_a_tiny_accidental_drag_still_counts_as_a_click(served):
    """A couple of pixels of hand-shake between press and release is a click, not an
    intent to draw a 3px shape."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        arm(page, "square")
        page.mouse.move(420, 360)
        page.mouse.down()
        page.mouse.move(422, 361)
        page.mouse.up()
        box = shape_box(page)
        browser.close()
    assert box["width"] == "80px" and box["height"] == "80px"


def test_one_undo_removes_a_drawn_shape(served):
    """Drawing is one creation, however many pointermoves it took."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        arm(page)
        page.mouse.move(400, 300)
        page.mouse.down()
        page.mouse.move(500, 360)
        page.mouse.move(560, 420)
        page.mouse.up()
        page.click("#wt-undo")
        gone = page.evaluate("() => !document.querySelector('svg.wt-shape')")
        browser.close()
    assert gone is True


def test_the_drawn_size_is_what_gets_recorded(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        arm(page)
        page.mouse.move(400, 300)
        page.mouse.down()
        page.mouse.move(560, 420)
        page.mouse.up()
        save(page)
        browser.close()
    patch = patches(tmp)[0]
    assert patch["op"] == "create"
    assert patch["changes"]["width"] == "160px"
    assert patch["changes"]["height"] == "120px"


def test_place_mode_ends_when_the_draw_ends(served):
    """One armed click draws one shape - the next press must select, not draw again."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        arm(page)
        page.mouse.move(400, 300)
        page.mouse.down()
        page.mouse.move(500, 380)
        page.mouse.up()
        state = page.evaluate(
            """() => ({
                hint: document.getElementById('wt-place-hint').hidden,
                placing: document.documentElement.classList.contains('wt-placing'),
                shapes: document.querySelectorAll('svg.wt-shape').length,
            })"""
        )
        page.click("#headline", position={"x": 8, "y": 8})
        after = page.evaluate(
            """() => ({
                tag: document.getElementById('wt-seltag').textContent,
                shapes: document.querySelectorAll('svg.wt-shape').length,
            })"""
        )
        browser.close()
    assert state == {"hint": True, "placing": False, "shapes": 1}
    assert after["tag"] == "h1#headline"   # a normal selection, not a second shape
    assert after["shapes"] == 1
