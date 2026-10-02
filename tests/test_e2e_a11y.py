"""Browser end-to-end test of keyboard focus around the suggestion and band lists.

The list items are real buttons, so a keyboard user reaches them with Tab and picks
with Enter. Closing the list hides the focused item, and the browser's focus fixup
then drops focus to <body> - the user loses their place and the next Tab starts again
from the top of the bar. The Overlay hands focus back to the list's toggle instead.
Driven with the keyboard only, the way the user it protects works.
"""

import pytest

from conftest import open_page

from _browser import sync_playwright, pytestmark  # noqa: F401

# (toggle id, list id) - the Font field's suggestions, and the band picker in the bar
LISTS = [
    pytest.param("wt-ff-toggle", "wt-ff-list", id="font-suggest"),
    pytest.param("wt-scope-toggle", "wt-scope-list", id="band-picker"),
]


def active_id(page):
    return page.evaluate("document.activeElement.id || document.activeElement.tagName")


def list_hidden(page, list_id):
    return page.eval_on_selector(f"#{list_id}", "el => el.hidden")


def open_by_keyboard(page, toggle, list_id):
    """Select an element, focus the toggle, open its list with Enter and Tab to the
    first item. Guards that focus really is on an item inside the open list, so the
    assertions after it cannot pass vacuously from focus never having left the toggle.
    """
    page.click("#headline")
    page.focus(f"#{toggle}")
    page.keyboard.press("Enter")
    assert not list_hidden(page, list_id)
    page.keyboard.press("Tab")
    assert page.evaluate(
        "id => document.getElementById(id).contains(document.activeElement)", list_id
    )


@pytest.mark.parametrize("toggle, list_id", LISTS)
def test_picking_an_item_returns_focus_to_the_toggle(served, toggle, list_id):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        open_by_keyboard(page, toggle, list_id)
        page.keyboard.press("Enter")
        focused, hidden = active_id(page), list_hidden(page, list_id)
        browser.close()
    assert hidden
    assert focused == toggle


@pytest.mark.parametrize("toggle, list_id", LISTS)
def test_escape_returns_focus_to_the_toggle(served, toggle, list_id):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        open_by_keyboard(page, toggle, list_id)
        page.keyboard.press("Escape")
        focused, hidden = active_id(page), list_hidden(page, list_id)
        selected_tag = page.inner_text("#wt-seltag")
        browser.close()
    assert hidden
    assert focused == toggle
    assert selected_tag   # Esc dismissed the list, not the selection behind it


@pytest.mark.parametrize("toggle, list_id", LISTS)
def test_an_outside_click_does_not_take_focus_back(served, toggle, list_id):
    """Only a close from inside the list restores focus. Clicking another field closes
    the list too, and the user's choice of where to go next must stand."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        page.focus(f"#{toggle}")
        page.keyboard.press("Enter")
        assert not list_hidden(page, list_id)
        page.click("#wt-w")
        focused, hidden = active_id(page), list_hidden(page, list_id)
        browser.close()
    assert hidden
    assert focused == "wt-w"


# (toggle id, list id, the field's own text input)
LISTS_WITH_INPUT = [
    pytest.param("wt-ff-toggle", "wt-ff-list", "wt-ff", id="font-suggest"),
    pytest.param("wt-scope-toggle", "wt-scope-list", "wt-scope-input", id="band-picker"),
]


@pytest.mark.parametrize("toggle, list_id, input_id", LISTS_WITH_INPUT)
def test_escape_from_outside_the_list_leaves_focus_alone(served, toggle, list_id, input_id):
    """The case the "focus was inside the list" guard exists for. The outside-click case
    above never reaches it (that close does not go through the focus-returning path),
    but Esc does: with the list open and focus moved back into the field's own input,
    Esc still closes the list, and must not yank focus out of the field being typed in."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        page.focus(f"#{toggle}")
        page.keyboard.press("Enter")
        assert not list_hidden(page, list_id)
        page.focus(f"#{input_id}")
        assert not list_hidden(page, list_id)   # moving focus alone does not close it
        page.keyboard.press("Escape")
        focused, hidden = active_id(page), list_hidden(page, list_id)
        browser.close()
    assert hidden   # Esc really took the dismiss path, so the guard was exercised
    assert focused == input_id
