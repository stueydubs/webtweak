"""Browser end-to-end test of redo and the history buttons.

Undo was one-way and invisible: nothing on screen said it existed or whether
anything was left to undo, and stepping back too far meant redoing the work by
hand. Redo is built by having the undo path produce an inverse batch, so the same
applier runs in both directions - which is why these tests care as much about the
state left behind (the change list, the unsaved-changes flag) as about the page.
"""

from conftest import open_page, patches, place_shape, save, set_field

from _browser import sync_playwright, pytestmark  # noqa: F401


def history(page):
    return page.evaluate("""() => ({
        undo: document.getElementById('wt-undo').disabled,
        redo: document.getElementById('wt-redo').disabled,
    })""")


def shapes(page):
    return page.evaluate("() => document.querySelectorAll('svg.wt-shape').length")


def test_the_buttons_track_their_stacks(served):
    """History is legible at a glance, which is also what makes undo discoverable."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        fresh = history(page)
        set_field(page, "#wt-fs", "52")      # nothing selected yet: no-op
        page.click("#headline")
        set_field(page, "#wt-fs", "52")
        after_edit = history(page)
        page.click("#wt-undo")
        after_undo = history(page)
        page.click("#wt-redo")
        after_redo = history(page)
        browser.close()
    assert fresh == {"undo": True, "redo": True}
    assert after_edit == {"undo": False, "redo": True}
    assert after_undo == {"undo": True, "redo": False}
    assert after_redo == {"undo": False, "redo": True}


def test_redo_restores_an_undone_property_change(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        set_field(page, "#wt-fs", "52")
        page.click("#wt-undo")
        undone = page.eval_on_selector("#headline", "el => getComputedStyle(el).fontSize")
        page.click("#wt-redo")
        redone = page.eval_on_selector("#headline", "el => getComputedStyle(el).fontSize")
        field = page.eval_on_selector("#wt-fs", "el => el.value")
        save(page)
        browser.close()
    assert undone == "44px"                                    # the authored size
    assert redone == "52px"
    assert field == "52px"                                     # the panel came back too
    assert patches(tmp)[0]["changes"]["font-size"] == "52px"


def test_both_keyboard_bindings_redo(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        set_field(page, "#wt-fs", "52")
        page.keyboard.press("Control+z")
        page.keyboard.press("Shift+Control+z")
        by_shift = page.eval_on_selector("#headline", "el => getComputedStyle(el).fontSize")
        page.keyboard.press("Control+z")
        page.keyboard.press("Control+y")
        by_ctrl_y = page.eval_on_selector("#headline", "el => getComputedStyle(el).fontSize")
        browser.close()
    assert by_shift == "52px"
    assert by_ctrl_y == "52px"


def test_redo_restores_an_undone_shape_creation(served):
    """Creation and removal are exact inverses in the undo vocabulary, so undoing a
    creation yields a removal step - and redoing it puts the shape back where it was,
    with its edits, not as a fresh one."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        place_shape(page)
        set_field(page, "#wt-fill", "#00ff00")     # an edit that must survive the round trip
        page.click("#wt-undo")                     # undoes the fill
        page.click("#wt-undo")                     # undoes the creation
        gone = shapes(page)
        page.click("#wt-redo")                     # back it comes
        back = shapes(page)
        where = page.eval_on_selector(
            "svg.wt-shape", "el => el.parentElement.tagName.toLowerCase()")
        page.click("#wt-redo")                     # and the fill on top of it
        fill = page.eval_on_selector("svg.wt-shape", "el => getComputedStyle(el).fill")
        save(page)
        browser.close()
    assert gone == 0 and back == 1
    assert where == "body"                          # reinserted into its own parent
    assert fill == "rgb(0, 255, 0)"
    create = next(p for p in patches(tmp) if p.get("op") == "create")
    assert create["changes"]["fill"] == "#00ff00"


def test_a_redone_shape_returns_to_its_place_not_the_end(served):
    """"In the right place in the document" needs a following sibling to mean
    anything: a shape is appended to <body>, so with nothing after it a reinsertion
    and a plain append look identical. Two shapes, and the first must come back
    BEFORE the second.
    """
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        place_shape(page, "square", 380, 380)
        place_shape(page, "circle", 520, 380)
        order = "() => [...document.querySelectorAll('svg.wt-shape')].map(e => e.dataset.wtShape)"
        page.click("#wt-undo")                 # undo the circle's creation
        page.click("#wt-undo")                 # undo the square's creation
        page.click("#wt-redo")                 # square back first
        page.click("#wt-redo")                 # then the circle
        both = page.evaluate(order)
        # and now the interesting direction: remove the FIRST of the two, put it back
        page.click("svg.wt-shape")             # select the square
        page.click("#wt-reset")                # remove it
        page.click("#wt-undo")                 # reinsert it - before the circle, not after
        restored = page.evaluate(order)
        browser.close()
    assert both == ["square", "circle"]
    assert restored == ["square", "circle"]


def test_redo_after_an_undone_shape_removal_removes_it_again(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        place_shape(page)
        page.click("#wt-reset")            # removing a shape is itself undoable
        removed = shapes(page)
        page.click("#wt-undo")             # brought back
        restored = shapes(page)
        page.click("#wt-redo")             # removed again
        removed_again = shapes(page)
        browser.close()
    assert removed == 0
    assert restored == 1
    assert removed_again == 0


def test_a_redone_gesture_stays_its_own_undo_step(served):
    """A drag or resize is one undo step that never fuses with later typing of the
    same property. Its inverse has to carry that too, or the step would come back off
    the redo stack collapsible - and a later keystroke would swallow the whole resize.
    """
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        place_shape(page)
        out = page.evaluate("""() => {
            const svg = document.querySelector('svg.wt-shape');
            const grip = document.querySelector('#wt-selected .wt-grip-r');   // width only
            const gr = grip.getBoundingClientRect();
            const x = gr.x + gr.width / 2, y = gr.y + gr.height / 2;
            const opts = id => ({ bubbles: true, pointerId: id });
            grip.dispatchEvent(new PointerEvent('pointerdown', {...opts(1), clientX: x, clientY: y}));
            grip.dispatchEvent(new PointerEvent('pointermove', {...opts(1), clientX: x + 40, clientY: y}));
            grip.dispatchEvent(new PointerEvent('pointerup', {...opts(1), clientX: x + 40, clientY: y}));
            const afterGrip = svg.style.width;
            document.getElementById('wt-undo').click();
            const afterUndo = svg.style.width;
            document.getElementById('wt-redo').click();
            const afterRedo = svg.style.width;
            // now type the same property, then step back once
            const w = document.getElementById('wt-w');
            w.value = '150'; w.dispatchEvent(new Event('input', { bubbles: true }));
            document.getElementById('wt-undo').click();
            return { afterGrip, afterUndo, afterRedo, afterTypedUndo: svg.style.width };
        }""")
        browser.close()
    assert out["afterGrip"] == "120px"
    assert out["afterUndo"] == "80px"          # the shape's seeded width
    assert out["afterRedo"] == "120px"         # the whole gesture came back
    assert out["afterTypedUndo"] == "120px"    # and did not fuse with the typing


def test_a_new_edit_clears_the_redo_stack(served):
    """Stepping forward must never splice an abandoned branch of history into work
    that has moved on."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        set_field(page, "#wt-fs", "52")
        page.click("#wt-undo")
        before = history(page)
        set_field(page, "#wt-ls", "2px")   # a different property: a new branch
        after = history(page)
        page.keyboard.press("Shift+Control+z")   # must do nothing
        size = page.eval_on_selector("#headline", "el => getComputedStyle(el).fontSize")
        save(page)
        browser.close()
    assert before["redo"] is False          # there was something to redo
    assert after["redo"] is True            # and the new edit dropped it
    assert size == "44px"                    # the abandoned branch did not come back
    assert patches(tmp)[0]["changes"] == {"letter-spacing": "2px"}


def test_the_change_list_and_unsaved_state_survive_a_round_trip(served):
    """After any undo or redo the session's own view of itself is recomputed, so the
    save prompt and the reconcile badge stay honest."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        set_field(page, "#wt-fs", "52")
        page.click("#wt-undo")
        after_undo = page.evaluate("""() => ({
            list: document.getElementById('wt-changes').hidden,
            head: document.getElementById('wt-changes-head').textContent,
        })""")
        page.click("#wt-save")             # nothing left to save
        empty_save = page.eval_on_selector("#wt-status", "el => el.textContent")
        page.click("#wt-redo")
        after_redo = page.evaluate(
            "() => document.getElementById('wt-changes-head').textContent")
        save(page)
        badge = page.eval_on_selector("#wt-badge", "el => el.textContent")
        browser.close()
    assert after_undo["list"] is True                  # no changes, so no list
    assert empty_save == "nothing changed yet"
    assert "1 element changed" in after_redo
    assert badge == "1 pending"
    assert len(patches(tmp)) == 1


def test_the_hint_mentions_redo(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        hint = page.eval_on_selector(".wt-hint", "el => el.textContent")
        browser.close()
    assert "redo" in hint.lower()
