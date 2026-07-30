"""Browser end-to-end test of the select-edit-save loop.

Requires Playwright: `pip install playwright && playwright install chromium`.
Skips LOUDLY (with that reason) when Playwright is absent, so a reader knows the
browser-side loop is unverified rather than assuming it's green. The same loop is
also verified interactively during development via the Playwright MCP.
"""

import json
import shutil

import pytest

from conftest import edit, open_page, place_shape, select_card

from _browser import sync_playwright, pytestmark  # noqa: F401


def _drag(page, box, dx, dy, steps=8):
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx + dx, cy + dy, steps=steps)
    page.mouse.up()


def _box(page, sel):
    return page.eval_on_selector(sel, """el => {
        const r = el.getBoundingClientRect();
        return {x: r.x, y: r.y, width: r.width, height: r.height};
    }""")


def test_hover_recovers_after_escape_during_drag(served):
    """Pressing Esc mid-drag tears interact down without an 'end' event; the overlay
    must still reset `interacting` so the hover box keeps working afterwards."""
    tmp, port = served
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        select_card(page)
        box = _box(page, ".card")
        # start a drag and press Esc before releasing (interact.unset, no 'end' fires)
        cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        page.mouse.move(cx, cy)
        page.mouse.down()
        page.mouse.move(cx + 20, cy + 10, steps=4)
        page.keyboard.press("Escape")
        page.mouse.up()
        # hover over the headline - the hover box must appear (interacting was reset)
        hb = page.eval_on_selector("#headline", """el => {
            const r = el.getBoundingClientRect(); return {x: r.x, y: r.y};
        }""")
        page.mouse.move(hb["x"] + 5, hb["y"] + 5)
        shown = page.eval_on_selector("#wt-hover", "el => !el.hidden")
        browser.close()
    assert shown   # hover feedback still works after an Esc-interrupted drag


def test_select_edit_nudge_resize_save_loop(served):
    tmp, port = served
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")

        # --- select + property change ---
        page.click("#headline")
        assert page.eval_on_selector("#wt-seltag", "el => el.textContent") == "h1#headline"
        page.fill("#wt-fs", "52")
        page.dispatch_event("#wt-fs", "input")
        assert page.eval_on_selector("#headline", "el => getComputedStyle(el).fontSize") == "52px"

        # --- nudge: drag the card interior leftward ---
        select_card(page)
        cardbox = _box(page, ".card")
        _drag(page, cardbox, -24, 0)

        # --- resize: drag the bottom-right grip outward ---
        # Re-read the box: the nudge above moved the card, so the pre-drag
        # coordinates no longer point at the grip.
        cardbox = _box(page, ".card")
        page.mouse.move(cardbox["x"] + cardbox["width"] - 3, cardbox["y"] + cardbox["height"] - 3)
        page.mouse.down()
        page.mouse.move(cardbox["x"] + cardbox["width"] + 30,
                        cardbox["y"] + cardbox["height"] + 20, steps=8)
        page.mouse.up()

        # --- save ---
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.startsWith('saved')"
        )
        browser.close()

    edits = json.loads((tmp / "sample.webtweak.json").read_text())
    batch = edits["batches"][0]
    assert batch["status"] == "pending"
    assert batch["viewport"] == 1280  # stamped from the real browser window.innerWidth
    patches = {p["fingerprint"].get("id") or p["fingerprint"]["selector"]: p
               for p in batch["patches"]}

    # the headline font-size change
    h1 = patches["headline"]
    assert h1["changes"]["font-size"] == "52px"

    # the card carries a 4px-snapped nudge and a resize. Match the card itself,
    # not a descendant whose positional selector also contains "card".
    card = next(p for k, p in patches.items() if k.endswith("div.card"))
    assert "nudge" in card["changes"]
    assert card["changes"]["nudge"]["dx"] % 4 == 0
    assert "width" in card["changes"] and "height" in card["changes"]


def test_create_shape_change_fill_save(served):
    """Draw a shape from the palette, set its fill, save: a op:'create' patch lands
    carrying the shape kind, geometry, anchor, and a self-contained changes snapshot."""
    tmp, port = served
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")

        place_shape(page, "triangle", 400, 350)
        # the dropped <svg> is selected, and the panel shows Shape / hides Type
        assert page.eval_on_selector("#wt-seltag", "el => el.textContent").startswith("svg#wt-shape-")
        vis = page.evaluate("""() => ({
            shape: document.querySelector('.wt-group[data-group="Shape"]').hidden,
            type: document.querySelector('.wt-group[data-group="Type"]').hidden,
            box: document.querySelector('.wt-group[data-group="Box"]').hidden,
        })""")
        assert vis == {"shape": False, "type": True, "box": False}

        # change the fill - it cascades from the <svg> wrapper to the child polygon
        page.evaluate("""() => {
            const f = document.getElementById('wt-fill');
            f.value = '#3366cc';
            f.dispatchEvent(new Event('input', { bubbles: true }));
        }""")
        assert page.eval_on_selector("svg.wt-shape polygon",
                                     "el => getComputedStyle(el).fill") == "rgb(51, 102, 204)"

        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.startsWith('saved')"
        )
        browser.close()

    batch = json.loads((tmp / "sample.webtweak.json").read_text())["batches"][0]
    create = next(p for p in batch["patches"] if p.get("op") == "create")
    assert create["shape"] == "triangle"
    assert create["renderer"] == "svg"
    assert create["geometry"]["el"] == "polygon"          # self-describing inner SVG
    assert create["anchor"]["position"] == "append"
    assert create["fingerprint"]["id"].startswith("wt-shape-")  # throwaway id reconcile strips
    ch = create["changes"]
    assert ch["fill"] == "#3366cc"                        # the control edit
    # self-contained even though only fill was touched: position + size were seeded
    assert ch["position"] == "absolute"
    assert ch["left"] == "400px" and ch["top"] == "350px"
    assert "width" in ch and "height" in ch


def test_created_shape_restored_after_reload(served):
    """A created shape re-injects via restore() after a reload, with its edits intact."""
    tmp, port = served
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")

        place_shape(page, "star", 500, 300)
        page.evaluate("""() => {
            const f = document.getElementById('wt-fill');
            f.value = '#11aa55';
            f.dispatchEvent(new Event('input', { bubbles: true }));
        }""")
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.startsWith('saved')"
        )

        page.reload()
        page.wait_for_selector("#wt-root")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.indexOf('restored') !== -1"
        )
        state = page.evaluate("""() => {
            const svg = document.querySelector('svg.wt-shape');
            return svg ? {
                kind: svg.getAttribute('data-wt-shape'),
                fill: getComputedStyle(svg.firstElementChild).fill,
            } : null;
        }""")
        browser.close()

    assert state == {"kind": "star", "fill": "rgb(17, 170, 85)"}  # shape + edit survived reload


def test_shape_resizes_via_grip(served):
    """A shape resizes by grabbing the visible grip handle directly (the grip sits at
    the box edge; the overlay drives resize off it, not interact's inside-the-edge band
    that users kept missing)."""
    tmp, port = served
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")

        place_shape(page, "circle", 400, 350)   # circle: transparent corners, worst case
        before = page.eval_on_selector("svg.wt-shape",
            "el => ({ w: el.style.width, h: el.style.height })")
        # grab the bottom-right grip at its real on-screen centre and drag outward
        grip = page.eval_on_selector("#wt-selected .wt-grip-br", """el => {
            const r = el.getBoundingClientRect();
            return { cx: r.x + r.width / 2, cy: r.y + r.height / 2 };
        }""")
        page.mouse.move(grip["cx"], grip["cy"])
        page.mouse.down()
        page.mouse.move(grip["cx"] + 50, grip["cy"] + 35, steps=10)
        page.mouse.up()
        after = page.eval_on_selector("svg.wt-shape",
            "el => ({ w: el.style.width, h: el.style.height })")
        browser.close()

    assert before == {"w": "80px", "h": "80px"}
    assert int(after["w"][:-2]) > 80 and int(after["h"][:-2]) > 80  # grew via the grip


def test_shape_drag_and_drop_from_palette(served):
    """Dragging a palette shape onto the page drops it at the release point (in addition
    to click-to-place)."""
    tmp, port = served
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")

        page.click("#wt-shape-btn")              # open the palette
        # native HTML5 drag-and-drop: dragstart on the item, drop on the page at (560, 420)
        placed = page.evaluate("""() => {
            const item = document.querySelector('.wt-shape-item[data-shape="diamond"]');
            const dt = new DataTransfer();
            item.dispatchEvent(new DragEvent('dragstart', { bubbles: true, dataTransfer: dt }));
            const placing = document.documentElement.classList.contains('wt-placing');
            const x = 560, y = 420, target = document.elementFromPoint(x, y);
            target.dispatchEvent(new DragEvent('dragover', { bubbles: true, dataTransfer: dt, clientX: x, clientY: y }));
            target.dispatchEvent(new DragEvent('drop', { bubbles: true, dataTransfer: dt, clientX: x, clientY: y }));
            item.dispatchEvent(new DragEvent('dragend', { bubbles: true, dataTransfer: dt }));
            const svg = document.querySelector('svg.wt-shape');
            return {
                placingDuringDrag: placing,
                kind: svg && svg.getAttribute('data-wt-shape'),
                left: svg && svg.style.left,
                top: svg && svg.style.top,
                selected: document.getElementById('wt-seltag').textContent.startsWith('svg#wt-shape-'),
                placeModeCleared: document.getElementById('wt-place-hint').hidden,
            };
        }""")
        browser.close()

    assert placed["placingDuringDrag"] is True
    assert placed["kind"] == "diamond"
    assert placed["left"] == "560px" and placed["top"] == "420px"  # dropped at the release point
    assert placed["selected"] is True
    assert placed["placeModeCleared"] is True


def test_palette_items_are_clickable_with_an_element_selected(served):
    """The palette drops out of the bar into the properties panel's column. The panel
    is a later sibling in the overlay root, so without the bar winning on z-index the
    right-hand palette items paint *under* it and cannot be clicked at all - and only
    while something is selected, which is most of the time.
    """
    tmp, port = served
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        page.click("#headline")                  # panel open, over the palette's column
        page.click("#wt-shape-btn")
        # the 3rd item of a 3-column grid: the far right of the palette, deepest
        # under the panel. A real click, so Playwright's hit-testing does the checking.
        page.click('.wt-shape-item[data-shape="circle"]')
        page.mouse.click(420, 420)
        kind = page.eval_on_selector("svg.wt-shape", "el => el.dataset.wtShape")
        browser.close()
    assert kind == "circle"


def test_shape_stroke_width_one_and_black_border_record(served):
    """Regression: a shape has no authored baseline, so a 1px border width or a
    #000000 stroke must be recorded - not mistaken for a 'revert' against the SVG UA
    default the baseline peel resolves to, which would silently drop it from the patch."""
    tmp, port = served
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        place_shape(page, "square", 400, 350)
        page.evaluate("""() => {
            const sw = document.getElementById('wt-sw');
            sw.value = '1'; sw.dispatchEvent(new Event('input', { bubbles: true }));
            const st = document.getElementById('wt-stroke');
            st.value = '#000000'; st.dispatchEvent(new Event('input', { bubbles: true }));
        }""")
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.startsWith('saved')"
        )
        browser.close()
    create = next(p for p in json.loads((tmp / "sample.webtweak.json").read_text())
                  ["batches"][0]["patches"] if p.get("op") == "create")
    assert create["changes"]["stroke-width"] == "1px"   # not swallowed as a revert
    assert create["changes"]["stroke"] == "#000000"     # black border is recordable


def test_shape_rx_radius_routes_to_child_and_patch(served):
    """The Radius control writes rx onto the child <rect> (not the <svg>), the field
    shows only for rect/square, and the value lands in the create patch."""
    tmp, port = served
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        place_shape(page, "square", 400, 350)
        radius_shown = page.eval_on_selector("#wt-rx", "el => !el.closest('.wt-field').hidden")
        page.evaluate("""() => {
            const r = document.getElementById('wt-rx');
            r.value = '14'; r.dispatchEvent(new Event('input', { bubbles: true }));
        }""")
        child_rx = page.eval_on_selector("svg.wt-shape rect", "el => getComputedStyle(el).rx")
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.startsWith('saved')"
        )
        browser.close()
    assert radius_shown is True
    assert child_rx == "14px"                            # applied to the child <rect>
    create = next(p for p in json.loads((tmp / "sample.webtweak.json").read_text())
                  ["batches"][0]["patches"] if p.get("op") == "create")
    assert create["changes"]["rx"] == "14px"


def test_number_floors_differ_by_what_zero_means(served):
    """stroke-width and rx are 0-meaningful (no border / sharp corners) so they floor
    at 0, while font-size floors at 1. Asserted through the controls rather than
    through a `min` attribute: font-size is a stepper now, so its floor lives in the
    step arithmetic instead of in the markup, and the guarantee is what matters.
    """
    tmp, port = served
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        shape_mins = page.evaluate("""() => ({
            sw: document.getElementById('wt-sw').getAttribute('min'),
            rx: document.getElementById('wt-rx').getAttribute('min'),
        })""")
        # font-size: step down from 1px and it must not go below 1
        page.click("#headline")
        page.fill("#wt-fs", "1px")
        page.dispatch_event("#wt-fs", "input")
        page.click("#wt-fs-down")
        page.click("#wt-fs-down")
        floored = page.eval_on_selector("#wt-fs", "el => el.value")
        browser.close()
    assert shape_mins == {"sw": "0", "rx": "0"}
    assert floored == "1px"


def test_grip_resize_and_panel_edit_are_separate_undo_steps(served):
    """A single-axis grip resize and a later panel edit of the same prop must be
    distinct undo steps: one Cmd+Z reverts only the panel edit, leaving the resize."""
    tmp, port = served
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        place_shape(page, "square", 400, 350)
        out = page.evaluate("""() => {
            const svg = document.querySelector('svg.wt-shape');
            const grip = document.querySelector('#wt-selected .wt-grip-r');  // width-only
            const gr = grip.getBoundingClientRect();
            const gx = gr.x + gr.width / 2, gy = gr.y + gr.height / 2;
            grip.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, clientX: gx, clientY: gy, pointerId: 1 }));
            grip.dispatchEvent(new PointerEvent('pointermove', { bubbles: true, clientX: gx + 40, clientY: gy, pointerId: 1 }));
            grip.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, clientX: gx + 40, clientY: gy, pointerId: 1 }));
            const afterGrip = svg.style.width;                       // ~120px
            const w = document.getElementById('wt-w');
            w.value = '150'; w.dispatchEvent(new Event('input', { bubbles: true }));
            document.dispatchEvent(new KeyboardEvent('keydown', { key: 'z', ctrlKey: true, bubbles: true }));
            return { afterGrip, afterUndo: svg.style.width };
        }""")
        browser.close()
    assert out["afterGrip"] == "120px"
    assert out["afterUndo"] == "120px"   # only the panel edit reverted; the grip resize stayed


def test_shape_lands_at_cursor_under_transform_scale(served):
    """Placement compensates for a transform:scale() ancestor (the containing block AND
    scaled) so the shape lands at the click point, not overshot by the scale factor."""
    tmp, port = served
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        page.evaluate("""() => {
            document.body.style.transform = 'scale(0.5)';
            document.body.style.transformOrigin = 'top left';
        }""")
        page.click("#wt-shape-btn")
        page.click('.wt-shape-item[data-shape="circle"]')
        page.mouse.click(500, 300)
        page.wait_for_selector("svg.wt-shape")
        landed = page.eval_on_selector("svg.wt-shape", """el => {
            const r = el.getBoundingClientRect();
            return Math.abs(r.left - 500) < 3 && Math.abs(r.top - 300) < 3;
        }""")
        browser.close()
    assert landed   # divided the viewport error by the on-screen scale


def test_undo_removes_a_created_shape(served):
    """Cmd/Ctrl+Z right after placing a shape removes it and deselects (ADR-0002)."""
    tmp, port = served
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        place_shape(page, "triangle", 400, 350)
        assert page.eval_on_selector_all("svg.wt-shape", "els => els.length") == 1
        page.evaluate(
            "() => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'z', ctrlKey: true, bubbles: true }))"
        )
        remaining = page.eval_on_selector_all("svg.wt-shape", "els => els.length")
        panel_hidden = page.eval_on_selector("#wt-panel", "el => el.hidden")
        browser.close()
    assert remaining == 0           # the shape was removed
    assert panel_hidden is True     # and the panel deselected


def test_shape_margin_reverts_but_seeded_props_persist(served):
    """A shape's seeded props (stroke-width/fill) have no baseline and always record,
    but a NON-seeded margin added then cleared on a shape reverts normally - it must
    not leave a stale no-op margin in the create patch."""
    tmp, port = served
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        place_shape(page, "square", 400, 350)
        orig = page.eval_on_selector("#wt-margin-top", "el => el.value")
        page.evaluate("""(orig) => {
            const mg = document.getElementById('wt-margin-top');
            mg.value = '20px'; mg.dispatchEvent(new Event('input', { bubbles: true }));
            mg.value = orig; mg.dispatchEvent(new Event('input', { bubbles: true }));  // revert
            const sw = document.getElementById('wt-sw');           // a seeded prop still records
            sw.value = '1'; sw.dispatchEvent(new Event('input', { bubbles: true }));
        }""", orig)
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.startsWith('saved')"
        )
        browser.close()
    create = next(p for p in json.loads((tmp / "sample.webtweak.json").read_text())
                  ["batches"][0]["patches"] if p.get("op") == "create")
    assert "margin" not in create["changes"]             # reverted margin dropped, not stale
    assert create["changes"]["stroke-width"] == "1px"    # seeded prop still recorded


def test_shape_lands_at_cursor_on_positioned_body(served):
    """Placement compensates for a positioned/offset <body> (the containing block for an
    absolute child) so the shape lands at the click point, not shifted by the offset."""
    tmp, port = served
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        page.evaluate("""() => {
            document.body.style.position = 'relative';
            document.body.style.margin = '40px';
            document.body.style.border = '10px solid transparent';
        }""")
        page.click("#wt-shape-btn")
        page.click('.wt-shape-item[data-shape="circle"]')
        page.mouse.click(600, 300)
        page.wait_for_selector("svg.wt-shape")
        landed = page.eval_on_selector("svg.wt-shape", """el => {
            const r = el.getBoundingClientRect();
            return Math.abs(r.left - 600) < 2 && Math.abs(r.top - 300) < 2;
        }""")
        browser.close()
    assert landed   # corrected for the 50px body offset, lands at the cursor


def test_idless_sibling_fingerprint(served):
    """Select the 2nd .section-title (no id) and assert its fingerprint disambiguates."""
    tmp, port = served
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        page.eval_on_selector_all(".section-title", "els => els[1].click()")
        page.fill("#wt-fs", "30")
        page.dispatch_event("#wt-fs", "input")
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.startsWith('saved')"
        )
        browser.close()

    fp = json.loads((tmp / "sample.webtweak.json").read_text())["batches"][0]["patches"][0]["fingerprint"]
    assert fp["id"] == ""
    assert ":nth-of-type(2)" in fp["selector"]   # exercises cssPath's sibling branch
    assert fp["ownText"]                          # non-empty own text for disambiguation
    assert fp["siblingIndex"] == 1               # 2nd among same tag+class siblings


def test_selection_box_tracks_a_reflowing_edit(served):
    """Changing font-size (not width/height) must re-fit the selection box."""
    tmp, port = served
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        edit(page, "#headline", "#wt-fs", "80")
        tracks = page.evaluate("""() => {
            const el = document.getElementById('headline').getBoundingClientRect();
            const box = document.getElementById('wt-selected').getBoundingClientRect();
            return Math.abs(el.height - box.height) < 2 && Math.abs(el.top - box.top) < 2;
        }""")
        browser.close()
    assert tracks  # the box followed the taller heading, not just width/height edits


def test_reset_clears_unsaved_state(served):
    """Editing then resetting the only element leaves nothing to save (no false dirty)."""
    tmp, port = served
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        edit(page, "#headline", "#wt-fs", "70")
        page.click("#wt-reset")
        page.click("#wt-save")
        status = page.eval_on_selector("#wt-status", "el => el.textContent")
        browser.close()
    assert status == "nothing changed yet"  # edited map emptied; no spurious unsaved-changes state


def test_width_height_disabled_on_inline_element(served):
    """Box controls are disabled for inline elements where width/height are inert."""
    tmp, port = served
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        page.click("code")  # an inline element
        disabled = page.evaluate(
            "() => document.getElementById('wt-w').disabled && document.getElementById('wt-h').disabled"
        )
        browser.close()
    assert disabled


def test_invalid_freetext_value_is_not_recorded(served):
    """A typo in a free-text field (rejected by the browser) must not become a patch."""
    tmp, port = served
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        page.click("#headline")
        page.fill("#wt-margin-top", "banana")      # invalid - browser drops it
        page.dispatch_event("#wt-margin-top", "input")
        page.fill("#wt-fs", "52")                  # a real edit so there is something to save
        page.dispatch_event("#wt-fs", "input")
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.startsWith('saved')"
        )
        browser.close()

    patch = json.loads((tmp / "sample.webtweak.json").read_text())["batches"][0]["patches"][0]
    assert not [k for k in patch["changes"] if k.startswith("margin")]        # the phantom value never made it in
    assert patch["changes"]["font-size"] == "52px"  # the genuine edit did


def test_a_rejected_value_warning_clears_on_the_next_edit(served):
    """The status line reports the most recent notable thing that happened. An
    'ignored invalid' warning has no timer, so it used to sit there through every
    later successful edit - reading as current long after it stopped being true."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        page.fill("#wt-margin-top", "banana")        # rejected
        page.dispatch_event("#wt-margin-top", "input")
        warned = page.eval_on_selector("#wt-status", "el => el.textContent")
        page.fill("#wt-fs", "52")                    # a real edit supersedes it
        page.dispatch_event("#wt-fs", "input")
        after_edit = page.eval_on_selector("#wt-status", "el => el.textContent")
        page.fill("#wt-fs", "")                      # so does abandoning one
        page.dispatch_event("#wt-fs", "input")
        page.fill("#wt-margin-top", "banana")
        page.dispatch_event("#wt-margin-top", "input")
        page.fill("#wt-ls", "0.05em")
        page.dispatch_event("#wt-ls", "input")
        page.fill("#wt-ls", "")
        page.dispatch_event("#wt-ls", "input")
        after_revert = page.eval_on_selector("#wt-status", "el => el.textContent")
        browser.close()
    assert warned.startswith("ignored invalid margin-top")
    assert after_edit == ""
    assert after_revert == ""


def test_probing_a_value_leaves_no_mark_on_the_page(served):
    """The revert-comparison for margin/padding/box-shadow resolves a typed value by
    writing it to the element, reading computed style, and putting the inline style
    back. Restoring via `cssText = ""` CREATES an empty style attribute on an element
    that never had one - so merely typing in a field left a mark on the page, which is
    the one thing ADR-0001 promises the Overlay never does.
    """
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        page.fill("#wt-margin-top", "banana")        # rejected, but still probed
        page.dispatch_event("#wt-margin-top", "input")
        after_probe = page.eval_on_selector("#headline", "el => el.hasAttribute('style')")
        page.fill("#wt-fs", "52")                    # a real edit does earn one
        page.dispatch_event("#wt-fs", "input")
        during_edit = page.eval_on_selector("#headline", "el => el.getAttribute('style')")
        page.fill("#wt-fs", "")                      # and abandoning it takes it away again
        page.dispatch_event("#wt-fs", "input")
        after_revert = page.eval_on_selector("#headline", "el => el.hasAttribute('style')")
        browser.close()
    assert after_probe is False
    assert "font-size: 52px" in during_edit
    assert after_revert is False


def test_the_change_list_header_does_not_outlive_its_rows(served):
    """Reverting the last change hides the list but used to leave its header reading
    '1 element changed'. Invisible to the user, but it is the panel's own account of
    the session, and it was wrong."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        page.fill("#wt-fs", "52")
        page.dispatch_event("#wt-fs", "input")
        with_one = page.eval_on_selector("#wt-changes-head", "el => el.textContent")
        page.fill("#wt-fs", "")
        page.dispatch_event("#wt-fs", "input")
        after = page.evaluate("""() => ({
            head: document.getElementById('wt-changes-head').textContent,
            hidden: document.getElementById('wt-changes').hidden,
        })""")
        browser.close()
    assert "1 element changed" in with_one
    assert after["hidden"] is True
    assert "element changed" not in after["head"]


def test_revert_to_original_after_reload_clears_the_batch(served):
    """Edit + save, reload, then set the value back to its true original: the saved
    batch must be cleared, not left on disk with a no-op patch (baseline-drift)."""
    tmp, port = served
    edits_file = tmp / "sample.webtweak.json"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        original_fs = page.eval_on_selector("#headline", "el => getComputedStyle(el).fontSize")
        edit(page, "#headline", "#wt-fs", "72")
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.startsWith('saved')"
        )
        assert len(json.loads(edits_file.read_text())["batches"]) == 1

        page.reload()
        page.wait_for_selector("#wt-root")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.indexOf('restored') !== -1"
        )
        page.click("#headline")
        page.fill("#wt-fs", str(int(float(original_fs[:-2]))))  # back to the authored size
        page.dispatch_event("#wt-fs", "input")
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.indexOf('cleared') !== -1"
        )
        browser.close()

    # the revert is persisted: the pending batch is gone, not a no-op patch on disk
    assert json.loads(edits_file.read_text())["batches"] == []


def test_inline_replaced_element_keeps_size_controls(served):
    """A bare inline <img> is display:inline but replaced - it DOES honour width/
    height and transform, so its size controls must stay enabled (unlike <code>)."""
    tmp, port = served
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        # inject a bare inline image and select it
        page.evaluate("""() => {
            const img = document.createElement('img');
            img.src = 'data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==';
            img.id = 'probe-img'; img.width = 30; img.height = 30;
            document.querySelector('main p').appendChild(img);
        }""")
        page.click("#probe-img")
        state = page.evaluate("""() => ({
            display: getComputedStyle(document.getElementById('probe-img')).display,
            wDisabled: document.getElementById('wt-w').disabled,
            hDisabled: document.getElementById('wt-h').disabled,
        })""")
        browser.close()
    assert state["display"] == "inline"        # it really is an inline box...
    assert not state["wDisabled"]              # ...but replaced, so width stays editable
    assert not state["hDisabled"]


def test_edits_restored_after_reload(served):
    """An edit survives a reload via restore() (session persisted in sessionStorage)."""
    tmp, port = served
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        edit(page, "#headline", "#wt-fs", "60")
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.startsWith('saved')"
        )

        page.reload()
        page.wait_for_selector("#wt-root")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.indexOf('restored') !== -1"
        )
        size = page.eval_on_selector("#headline", "el => getComputedStyle(el).fontSize")
        browser.close()

    assert size == "60px"  # the edit was re-applied after reload


def _seed_batch(edits_file, session, patches):
    """Write an edits file holding one pending batch for `session`."""
    edits_file.write_text(json.dumps({
        "target": "sample.html",
        "batches": [{"sessionId": session, "savedAt": "2026-01-01T00:00:00",
                     "viewport": 1280, "status": "pending", "patches": patches}],
    }))


def test_partial_restore_preserves_unrelocated_patches(served):
    """If a reload can't re-locate some patched elements, the next save must NOT
    drop them - the un-relocated patches are preserved on disk (capture-intent)."""
    tmp, port = served
    edits_file = tmp / "sample.webtweak.json"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        session = page.evaluate("() => sessionStorage.getItem('wt-session-sample.html')")

        # one locatable patch (headline) + one that no longer exists in source (ghost)
        _seed_batch(edits_file, session, [
            {"fingerprint": {"tag": "h1", "id": "headline", "classes": ["title"],
                             "text": "", "ownText": "", "selector": "#headline",
                             "siblingIndex": 0, "openTag": "<h1 id=\"headline\">"},
             "changes": {"color": "#cc2222"}},
            {"fingerprint": {"tag": "span", "id": "ghost", "classes": [],
                             "text": "", "ownText": "", "selector": "#ghost",
                             "siblingIndex": 0, "openTag": "<span id=\"ghost\">"},
             "changes": {"font-size": "99px"}},
        ])
        page.reload()
        page.wait_for_selector("#wt-root")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.indexOf('restored') !== -1"
        )
        # make a real edit on the relocatable element and save
        edit(page, "#headline", "#wt-fs", "50")
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.startsWith('saved')"
        )
        browser.close()

    patches = json.loads(edits_file.read_text())["batches"][0]["patches"]
    ids = {p["fingerprint"]["id"] for p in patches}
    assert ids == {"headline", "ghost"}     # the ghost patch was NOT dropped
    ghost = next(p for p in patches if p["fingerprint"]["id"] == "ghost")
    assert ghost["changes"] == {"font-size": "99px"}   # preserved verbatim


def test_revert_preserves_authored_inline_longhand(served):
    """Reverting a margin edit on an element with an authored inline margin LONGHAND
    must restore the element's inline style verbatim, not strip the longhand."""
    tmp, port = served
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        page.evaluate("""() => {
            const box = document.createElement('div');
            box.id = 'lh-box';
            box.setAttribute('style', 'margin: 30px; margin-top: 50px; padding: 8px');
            box.textContent = 'box';
            document.querySelector('main').appendChild(box);
        }""")
        page.click("#lh-box")
        page.fill("#wt-margin-bottom", "12px")     # edit one side
        page.dispatch_event("#wt-margin-bottom", "input")
        page.fill("#wt-margin-bottom", "30px")     # back to the computed baseline
        page.dispatch_event("#wt-margin-bottom", "input")
        style = page.eval_on_selector("#lh-box", "el => el.getAttribute('style')")
        mt = page.eval_on_selector("#lh-box", "el => getComputedStyle(el).marginTop")
        browser.close()
    assert mt == "50px"                            # the authored longhand survived the revert
    assert "margin-top: 50px" in style             # inline restored verbatim
    assert "padding: 8px" in style


def test_missed_patch_superseded_by_fresh_edit(served):
    """A stranded (tag-guarded) patch must not produce a duplicate when the user edits
    the same element this session - the fresh patch supersedes it."""
    tmp, port = served
    edits_file = tmp / "sample.webtweak.json"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        session = page.evaluate("() => sessionStorage.getItem('wt-session-sample.html')")
        _seed_batch(edits_file, session, [
            {"fingerprint": {"tag": "div", "id": "headline", "classes": [], "text": "",
                             "ownText": "", "selector": "#headline", "siblingIndex": 0,
                             "openTag": "<div id=\"headline\">"},
             "changes": {"color": "#ff0000"}},   # tag mismatch -> stranded in missed[]
        ])
        page.reload()
        page.wait_for_selector("#wt-root")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.indexOf('restored') !== -1"
        )
        page.click("#headline")                  # edit the same element (an h1)
        page.fill("#wt-fs", "55")
        page.dispatch_event("#wt-fs", "input")
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.startsWith('saved')"
        )
        browser.close()
    patches = json.loads(edits_file.read_text())["batches"][0]["patches"]
    headline = [p for p in patches if p["fingerprint"]["id"] == "headline"]
    assert len(headline) == 1                     # not two conflicting patches
    assert headline[0]["fingerprint"]["tag"] == "h1"
    assert headline[0]["changes"] == {"font-size": "55px"}


def test_restore_skips_owntext_mismatch(served):
    """A patch whose selector resolves but whose recorded ownText no longer matches the
    located element must not be applied (guards against a positional-selector mis-hit)."""
    tmp, port = served
    edits_file = tmp / "sample.webtweak.json"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        session = page.evaluate("() => sessionStorage.getItem('wt-session-sample.html')")
        _seed_batch(edits_file, session, [
            {"fingerprint": {"tag": "p", "id": "", "classes": [],
                             "text": "", "ownText": "Totally different text from another element",
                             "selector": "body > main.wrap > p:nth-of-type(3)",
                             "siblingIndex": 0, "openTag": "<p>"},
             "changes": {"color": "#ff0000"}},
        ])
        page.reload()
        page.wait_for_selector("#wt-root")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.indexOf('restored') !== -1"
        )
        color = page.evaluate(
            "() => getComputedStyle(document.querySelectorAll('main p')[2]).color"
        )
        browser.close()
    assert color != "rgb(255, 0, 0)"   # the ownText mismatch blocked the wrong-element apply


def test_restore_skips_tag_mismatch(served):
    """An id that now resolves to a different tag than the fingerprint must not have
    its styles applied (guards a stale id moved to another element)."""
    tmp, port = served
    edits_file = tmp / "sample.webtweak.json"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        session = page.evaluate("() => sessionStorage.getItem('wt-session-sample.html')")
        # patch claims tag 'div' but #headline is an <h1>
        _seed_batch(edits_file, session, [
            {"fingerprint": {"tag": "div", "id": "headline", "classes": [],
                             "text": "", "ownText": "", "selector": "#headline",
                             "siblingIndex": 0, "openTag": "<div id=\"headline\">"},
             "changes": {"color": "#0000ff"}},
        ])
        page.reload()
        page.wait_for_selector("#wt-root")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.indexOf('restored') !== -1"
        )
        color = page.eval_on_selector("#headline", "el => getComputedStyle(el).color")
        browser.close()
    assert color != "rgb(0, 0, 255)"   # the mismatched patch was not applied


def test_in_session_save_then_revert_all_clears_batch(served):
    """Edit + save (persisted set by save, not restore), then revert in the SAME
    session and save again: the stale batch must clear without a reload."""
    tmp, port = served
    edits_file = tmp / "sample.webtweak.json"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        original_fs = page.eval_on_selector("#headline", "el => getComputedStyle(el).fontSize")
        edit(page, "#headline", "#wt-fs", "72")
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.startsWith('saved')"
        )
        assert len(json.loads(edits_file.read_text())["batches"]) == 1
        # revert in the same session - no reload, so persisted must have been set by save()
        page.fill("#wt-fs", str(int(float(original_fs[:-2]))))
        page.dispatch_event("#wt-fs", "input")
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.indexOf('cleared') !== -1"
        )
        browser.close()
    assert json.loads(edits_file.read_text())["batches"] == []


def test_box_control_width_entry_is_recorded(served):
    """Typing into the width box control records a patch (box controls bypass the
    CSS.supports gate - this guards that exemption)."""
    tmp, port = served
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        select_card(page)                # block element, width controls enabled
        page.fill("#wt-w", "350")
        page.dispatch_event("#wt-w", "input")
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.startsWith('saved')"
        )
        browser.close()
    patch = json.loads((tmp / "sample.webtweak.json").read_text())["batches"][0]["patches"][0]
    assert patch["changes"].get("width") == "350px"


def test_cleared_field_records_no_patch(served):
    """Clearing a control back to empty records nothing - including box controls,
    where parseInt('') would otherwise floor to 1px."""
    tmp, port = served
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        select_card(page)
        for field in ("#wt-fs", "#wt-w"):
            page.fill(field, "120")
            page.dispatch_event(field, "input")
            page.fill(field, "")
            page.dispatch_event(field, "input")
        page.click("#wt-save")
        status = page.eval_on_selector("#wt-status", "el => el.textContent")
        browser.close()
    assert status == "nothing changed yet"   # both fields ended empty; nothing recorded


def test_shorthand_spacing_revert_records_nothing(served):
    """A linked write emits the shorthand, so it needs the same revert detection the
    single margin box used to need: typing the value the element already has, resolved
    through the element, records no patch."""
    tmp, port = served
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        select_card(page)                     # .card { padding: 24px } - equal all round
        page.click("#wt-padding-link")        # link: one value, all four sides
        page.fill("#wt-padding-top", "24px")  # == the computed baseline
        page.dispatch_event("#wt-padding-top", "input")
        page.click("#wt-save")
        status = page.eval_on_selector("#wt-status", "el => el.textContent")
        browser.close()
    assert status == "nothing changed yet"
