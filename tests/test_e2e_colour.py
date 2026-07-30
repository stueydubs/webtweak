"""Browser end-to-end test of the hex field beside each colour swatch.

A bare `<input type="color">` shows a rectangle and nothing else: you cannot read
what colour the element currently is, and you cannot paste a brand hex into it. So
each swatch gains an editable hex beside it, and the two stay in step.
"""

from conftest import changes, open_page, save, select_card, set_field

from _browser import sync_playwright, pytestmark  # noqa: F401


def pair(page, control="wt-color"):
    return page.evaluate(
        """id => [document.getElementById(id).value,
                  document.getElementById(id + '-hex').value]""",
        control,
    )


def test_the_hex_shows_the_colour_the_element_already_is(served):
    """.lede is #44403a - previously invisible unless you opened the OS picker."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click(".lede")
        text = pair(page, "wt-color")
        browser.close()
    assert text == ["#44403a", "#44403a"]


def test_typing_a_hex_applies_and_records(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        set_field(page, "#wt-color-hex", "#7d5a3c")
        rendered = page.eval_on_selector("#headline", "el => getComputedStyle(el).color")
        swatch = pair(page, "wt-color")[0]
        save(page)
        browser.close()
    assert rendered == "rgb(125, 90, 60)"
    assert swatch == "#7d5a3c"          # the swatch followed the typed value
    assert changes(tmp) == {"color": "#7d5a3c"}


def test_a_hex_without_its_hash_still_works(served):
    """Pasting a brand colour out of a style guide often loses the #."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        set_field(page, "#wt-color-hex", "7d5a3c")
        save(page)
        browser.close()
    assert changes(tmp) == {"color": "#7d5a3c"}


def test_a_short_hex_is_accepted(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        set_field(page, "#wt-color-hex", "#f00")
        rendered = page.eval_on_selector("#headline", "el => getComputedStyle(el).color")
        save(page)
        browser.close()
    assert rendered == "rgb(255, 0, 0)"
    assert changes(tmp)["color"] in ("#f00", "#ff0000")


def test_a_half_typed_hex_records_nothing_and_does_not_nag(served):
    """Every keystroke fires an input event, so `#3f` arrives on the way to `#3fa9c2`.
    That is mid-typing, not a mistake - it must not record, and it must not put an
    'ignored invalid' warning up on every second keypress either."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        for partial in ("#", "#3", "#3f", "#3fa9c"):
            set_field(page, "#wt-color-hex", partial)
        status = page.eval_on_selector("#wt-status", "el => el.textContent")
        rendered = page.eval_on_selector("#headline", "el => getComputedStyle(el).color")
        page.click("#wt-save")
        saved = page.eval_on_selector("#wt-status", "el => el.textContent")
        browser.close()
    assert status == ""                       # silent, not nagging
    assert rendered == "rgb(26, 26, 26)"      # unchanged
    assert saved == "nothing changed yet"


def test_the_swatch_updates_the_hex(served):
    """Driven the other way round: the OS picker writes the swatch, and the hex has to
    follow or the two disagree about the same colour."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        set_field(page, "#wt-color", "#0000ff")
        both = pair(page, "wt-color")
        browser.close()
    assert both == ["#0000ff", "#0000ff"]


def test_every_colour_control_has_a_hex(served):
    """Text, Background, the border Colour, and a shape's Fill and Stroke."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        present = page.evaluate(
            """() => ['wt-color', 'wt-bg', 'wt-bc']
                .every(id => !!document.getElementById(id + '-hex'))"""
        )
        browser.close()
    assert present


def test_background_hex_records_independently(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        set_field(page, "#wt-bg-hex", "#efe9df")
        rendered = page.eval_on_selector(
            ".card", "el => getComputedStyle(el).backgroundColor")
        save(page)
        browser.close()
    assert rendered == "rgb(239, 233, 223)"
    assert changes(tmp) == {"background-color": "#efe9df"}
