"""Browser end-to-end test of the Shadow field and its presets.

Shadow is the one property in this release that resists discrete controls - four
lengths, a colour and an inset flag would be six controls for one declaration, and
a shadow's colour is almost always translucent while the panel's swatch is opaque
hex. So it stays a text field backed by the suggestion list the Font control
introduced: the property nobody remembers the syntax of becomes one you pick.

It is also the first suggestion list to sit at the bottom of the panel, which is a
scroll box - so the last test here is about the list being reachable at all.
"""

import json

from conftest import open_page, select_card, set_field

from _browser import sync_playwright, pytestmark  # noqa: F401

FIELD, TOGGLE, LIST = "#wt-shadow", "#wt-shadow-toggle", "#wt-shadow-list"


def save(page):
    page.click("#wt-save")
    page.wait_for_function(
        "document.getElementById('wt-status').textContent.startsWith('saved')"
    )


def changes(tmp, index=0):
    batch = json.loads((tmp / "sample.webtweak.json").read_text())["batches"][0]
    return batch["patches"][index]["changes"]


def presets(page):
    page.click(TOGGLE)
    return page.eval_on_selector_all(
        f"{LIST} .wt-suggest-item", "els => els.map(e => e.dataset.value)")


def shadow_of(page, selector):
    return page.eval_on_selector(selector, "el => getComputedStyle(el).boxShadow")


def test_presets_are_offered_and_include_one_that_removes_the_shadow(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        entries = presets(page)
        browser.close()
    assert "none" in entries                  # the one that removes it
    assert len(entries) >= 4                  # and a handful worth picking between
    assert any("inset" in e for e in entries)


def test_choosing_a_preset_applies_it_live_and_records_it(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        entries = presets(page)
        chosen = entries[1]                   # the first real shadow after `none`
        page.click(f"{LIST} .wt-suggest-item[data-value='{chosen}']")
        rendered = shadow_of(page, ".card")
        field = page.eval_on_selector(FIELD, "el => el.value")
        save(page)
        browser.close()
    assert rendered != "none"                 # it is on the page, not just in the field
    assert field == chosen
    assert changes(tmp) == {"box-shadow": chosen}


def test_typing_a_custom_shadow_applies_and_records(served):
    """The presets are a shortcut, not a cage."""
    tmp, port = served
    typed = "0 3px 9px rgba(122, 92, 62, 0.35)"
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        set_field(page, FIELD, typed)
        rendered = shadow_of(page, ".card")
        save(page)
        browser.close()
    assert rendered == "rgba(122, 92, 62, 0.35) 0px 3px 9px 0px"   # computed form
    assert changes(tmp) == {"box-shadow": typed}                   # recorded as authored


def test_typing_an_invalid_shadow_records_nothing(served):
    """No new handling needed - the existing invalid-value gate covers it, and this
    test is what says so."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        set_field(page, FIELD, "2px")          # incomplete, so the browser drops it
        status = page.eval_on_selector("#wt-status", "el => el.textContent")
        rendered = shadow_of(page, ".card")
        set_field(page, "#wt-fs", "20")        # a real edit, so there is a batch
        save(page)
        browser.close()
    assert status.startswith("ignored invalid box-shadow")
    assert rendered == "none"
    assert "box-shadow" not in changes(tmp)


def test_a_typo_does_not_destroy_a_shadow_already_set(served):
    """An invalid value resolves to the element's current computed value, which reads
    exactly like the user setting the field back to its baseline. Rejecting it before
    that comparison is what stops a stray keystroke from deleting the shadow.
    """
    tmp, port = served
    good = "0 8px 24px rgba(0, 0, 0, 0.18)"
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        set_field(page, FIELD, good)
        set_field(page, FIELD, "0 8px 24px rgba(0, 0")   # mid-typing garbage
        rendered = shadow_of(page, ".card")
        save(page)
        browser.close()
    assert rendered == "rgba(0, 0, 0, 0.18) 0px 8px 24px 0px"   # the good one survives
    assert changes(tmp) == {"box-shadow": good}


def test_clearing_the_shadow_field_reverts_the_change(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        set_field(page, FIELD, "0 8px 24px rgba(0, 0, 0, 0.2)")
        applied = shadow_of(page, ".card")
        set_field(page, FIELD, "")
        reverted = shadow_of(page, ".card")
        page.click("#wt-save")
        status = page.eval_on_selector("#wt-status", "el => el.textContent")
        browser.close()
    assert applied != "none"
    assert reverted == "none"
    assert status == "nothing changed yet"


def test_shadow_hides_with_the_border_group_for_a_shape(served):
    """It lives in the Border group, so it follows that group's visibility."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        on_element = page.eval_on_selector(FIELD, "el => !!el.offsetParent")
        page.click("#wt-shape-btn")
        page.click('.wt-shape-item[data-shape="circle"]')
        page.mouse.click(420, 360)
        on_shape = page.eval_on_selector(FIELD, "el => !!el.offsetParent")
        browser.close()
    assert on_element is True
    assert on_shape is False


def test_the_preset_list_is_reachable_on_a_short_window(served):
    """Shadow is the last field of the last group, and the panel is a scroll box - so
    a list positioned inside the panel would be clipped exactly here. Driven on a
    short window and by clicking the LAST preset: Playwright's own hit-testing fails
    if the row is not really there to click.
    """
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, height=640)
        select_card(page)
        entries = presets(page)
        last = entries[-1]
        geometry = page.evaluate(
            """() => {
                const l = document.getElementById('wt-shadow-list').getBoundingClientRect();
                const rows = [...document.querySelectorAll('#wt-shadow-list .wt-suggest-item')];
                const r = rows[rows.length - 1].getBoundingClientRect();
                const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
                return {inViewport: l.top >= 0 && l.bottom <= window.innerHeight,
                        lastRowHit: !!hit && hit.classList.contains('wt-suggest-item')};
            }"""
        )
        page.click(f"{LIST} .wt-suggest-item[data-value='{last}']")
        save(page)
        browser.close()
    assert geometry == {"inViewport": True, "lastRowHit": True}
    assert changes(tmp) == {"box-shadow": last}
