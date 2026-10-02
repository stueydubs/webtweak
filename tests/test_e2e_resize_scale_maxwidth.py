"""Overlay resize: percentage caps are not pinned, and the edge band honours a scaled ancestor (#38).

Part 1: getComputedStyle keeps `max-width: 100%` as a percentage, so a unit-blind
parseFloat read it as a 100px cap and every resize past 100px pinned a max-width the
user never asked for. Part 2: interact's edge-resize rect is viewport px, and under a
transform:scale() ancestor the first move wrote it as CSS px, halving the element.
"""

import pytest

from conftest import changes, edit, open_page, save, selected  # noqa: F401

from _browser import sync_playwright, pytestmark  # noqa: F401


def _inject(page, css, html):
    page.evaluate(
        """([css, html]) => {
            const st = document.createElement('style');
            st.textContent = css;
            document.head.appendChild(st);
            const host = document.createElement('div');
            host.id = 'rz-host';
            host.style.cssText = 'margin: 140px 0 0 40px';   // clear of the bar
            host.innerHTML = html;
            document.body.insertBefore(host, document.body.firstChild);
        }""",
        [css, html],
    )


def _grip_drag(page, dx, dy):
    """Drag the bottom-right grip of the current selection by (dx, dy) viewport px."""
    box = page.eval_on_selector(".wt-grip-br", """el => {
        const r = el.getBoundingClientRect();
        return {x: r.x + r.width / 2, y: r.y + r.height / 2};
    }""")
    page.mouse.move(box["x"], box["y"])
    page.mouse.down()
    page.mouse.move(box["x"] + dx, box["y"] + dy, steps=8)
    page.mouse.up()


def _resized_changes(served, cap):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        _inject(page,
                "#rz-parent { width: 800px; } "
                "#rz-box { width: 200px; height: 100px; max-width: %s; background: #ccc; }" % cap,
                '<div id="rz-parent"><div id="rz-box"></div></div>')
        page.click("#rz-box")
        assert selected(page) == "div#rz-box"
        _grip_drag(page, 150, 50)
        width = page.eval_on_selector("#rz-box", "el => el.style.width")
        save(page)
        browser.close()
    return width, changes(tmp)


def test_percentage_max_width_that_does_not_bind_is_not_pinned(served):
    width, ch = _resized_changes(served, "100%")
    assert width == "350px"          # the resize itself landed past 100px
    assert ch["width"] == "350px" and ch["height"] == "150px"
    assert "max-width" not in ch     # a 100% cap on an 800px parent is nowhere near binding


def test_px_max_width_that_binds_is_still_pinned(served):
    width, ch = _resized_changes(served, "200px")
    assert width == "350px"
    assert ch["max-width"] == "350px"   # the pin still works for a px cap


def test_percentage_max_width_that_binds_is_pinned(served):
    """A percentage that really does stop the drag (25% of 800 = 200px) still pins."""
    width, ch = _resized_changes(served, "25%")
    assert ch["max-width"] == "350px"


def test_edge_band_resize_under_scaled_ancestor_uses_css_pixels(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        _inject(page,
                "#rz-box { width: 400px; height: 200px; background: #ccc; }",
                '<div id="rz-box"></div>')
        page.evaluate("""() => {
            document.body.style.transform = 'scale(0.5)';
            document.body.style.transformOrigin = 'top left';
        }""")
        page.click("#rz-box", position={"x": 20, "y": 20})
        assert selected(page) == "div#rz-box"
        r = page.eval_on_selector("#rz-box", """el => {
            const r = el.getBoundingClientRect();
            return {right: r.right, bottom: r.bottom, w: r.width};
        }""")
        assert abs(r["w"] - 200) < 1       # the guard: the scale really is in force
        # Grab the edge band itself, clear of the 24px grip hit boxes: the right edge a
        # quarter of the way down, then the bottom edge a quarter of the way along. The
        # guard asserts each probe really lands on the element and not on a grip.
        def drag_from(px, py, dx, dy):
            grabbed = page.evaluate(
                "([x, y]) => { const e = document.elementFromPoint(x, y);"
                " return e ? (e.id || e.className) : ''; }", [px, py])
            assert "wt-grip" not in str(grabbed), grabbed
            page.mouse.move(px, py)
            page.mouse.down()
            page.mouse.move(px + dx, py + dy, steps=8)
            page.mouse.up()

        r = page.eval_on_selector("#rz-box", """el => {
            const r = el.getBoundingClientRect();
            return {left: r.left, top: r.top, right: r.right, bottom: r.bottom};
        }""")
        drag_from(r["right"] - 6, r["top"] + (r["bottom"] - r["top"]) / 4, 30, 0)
        r = page.eval_on_selector("#rz-box", """el => {
            const r = el.getBoundingClientRect();
            return {left: r.left, top: r.top, right: r.right, bottom: r.bottom};
        }""")
        drag_from(r["left"] + (r["right"] - r["left"]) / 4, r["bottom"] - 6, 0, 20)
        got = page.eval_on_selector("#rz-box", "el => ({w: el.style.width, h: el.style.height})")
        browser.close()
    # 30 and 20 viewport px are 60 and 40 CSS px under scale(0.5). Unfixed, the first
    # move wrote the viewport-px rect (about 200px) and the element halved.
    assert abs(float(got["w"][:-2]) - 460) <= 1, got
    assert abs(float(got["h"][:-2]) - 240) <= 1, got
