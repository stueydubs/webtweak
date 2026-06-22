"""Browser end-to-end test of the select-edit-save loop.

Requires Playwright: `pip install playwright && playwright install chromium`.
Skips LOUDLY (with that reason) when Playwright is absent, so a reader knows the
browser-side loop is unverified rather than assuming it's green. The same loop is
also verified interactively during development via the Playwright MCP.
"""

import json
import shutil

import pytest

from _server import make_page, start, stop

sync_api = pytest.importorskip(
    "playwright.sync_api",
    reason="install Playwright to run the browser e2e: "
           "pip install playwright && playwright install chromium",
)
from playwright.sync_api import sync_playwright  # noqa: E402


@pytest.fixture
def served():
    tmp, page = make_page()
    proc, port = start(page)
    yield tmp, port
    stop(proc)
    shutil.rmtree(tmp, ignore_errors=True)


def _drag(page, box, dx, dy, steps=8):
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx + dx, cy + dy, steps=steps)
    page.mouse.up()


def test_hover_recovers_after_escape_during_drag(served):
    """Pressing Esc mid-drag tears interact down without an 'end' event; the overlay
    must still reset `interacting` so the hover box keeps working afterwards."""
    tmp, port = served
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        page.click(".card")
        box = page.eval_on_selector(".card", """el => {
            const r = el.getBoundingClientRect();
            return {x: r.x, y: r.y, width: r.width, height: r.height};
        }""")
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
        page.click(".card")
        cardbox = page.eval_on_selector(".card", """el => {
            const r = el.getBoundingClientRect();
            return {x: r.x, y: r.y, width: r.width, height: r.height};
        }""")
        _drag(page, cardbox, -24, 0)

        # --- resize: drag the bottom-right grip outward ---
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

    # the card carries a 4px-snapped nudge and a resize
    card = next(p for k, p in patches.items() if "card" in k)
    assert "nudge" in card["changes"]
    assert card["changes"]["nudge"]["dx"] % 4 == 0
    assert "width" in card["changes"] and "height" in card["changes"]


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
        page.click("#headline")
        page.fill("#wt-fs", "80")
        page.dispatch_event("#wt-fs", "input")
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
        page.click("#headline")
        page.fill("#wt-fs", "70")
        page.dispatch_event("#wt-fs", "input")
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
        page.fill("#wt-margin", "banana")          # invalid - browser drops it
        page.dispatch_event("#wt-margin", "input")
        page.fill("#wt-fs", "52")                  # a real edit so there is something to save
        page.dispatch_event("#wt-fs", "input")
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.startsWith('saved')"
        )
        browser.close()

    patch = json.loads((tmp / "sample.webtweak.json").read_text())["batches"][0]["patches"][0]
    assert "margin" not in patch["changes"]        # the phantom value never made it in
    assert patch["changes"]["font-size"] == "52px"  # the genuine edit did


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
        page.click("#headline")
        page.fill("#wt-fs", "72")
        page.dispatch_event("#wt-fs", "input")
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
        page.click("#headline")
        page.fill("#wt-fs", "60")
        page.dispatch_event("#wt-fs", "input")
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
        page.click("#headline")
        page.fill("#wt-fs", "50")
        page.dispatch_event("#wt-fs", "input")
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
        page.fill("#wt-margin", "12px")            # edit margin (overrides all sides)
        page.dispatch_event("#wt-margin", "input")
        page.fill("#wt-margin", "50px 30px 30px 30px")  # revert to the computed baseline
        page.dispatch_event("#wt-margin", "input")
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
        page.click("#headline")
        page.fill("#wt-fs", "72")
        page.dispatch_event("#wt-fs", "input")
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
        page.click(".card")               # block element, width controls enabled
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
        page.click(".card")
        for field in ("#wt-fs", "#wt-w"):
            page.fill(field, "120")
            page.dispatch_event(field, "input")
            page.fill(field, "")
            page.dispatch_event(field, "input")
        page.click("#wt-save")
        status = page.eval_on_selector("#wt-status", "el => el.textContent")
        browser.close()
    assert status == "nothing changed yet"   # both fields ended empty; nothing recorded


def test_shorthand_margin_revert_records_nothing(served):
    """Typing a shorthand margin equal to the authored value (e.g. '32px 0' on the
    card) is recognised as a revert against the computed baseline, recording no patch."""
    tmp, port = served
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/sample.html")
        page.wait_for_selector("#wt-root")
        page.click(".card")               # .card { margin: 32px 0; }
        page.fill("#wt-margin", "32px 0")  # author shorthand == computed baseline
        page.dispatch_event("#wt-margin", "input")
        page.click("#wt-save")
        status = page.eval_on_selector("#wt-status", "el => el.textContent")
        browser.close()
    assert status == "nothing changed yet"   # shorthand resolved to baseline -> no record
