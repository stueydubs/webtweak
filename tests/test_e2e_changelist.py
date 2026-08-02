"""Browser e2e for the session change list.

`edited` holds the whole session but the properties panel only ever shows one
element, so reviewing a session meant saving and opening the JSON. The list has
to stay truthful as edits are added, undone, reset and restored - a stale count
would be worse than no list.
"""

import shutil

import pytest

from conftest import edit, open_page, selected

from _browser import sync_playwright, pytestmark  # noqa: F401


def head(page):
    return page.eval_on_selector("#wt-changes-head", "el => el.textContent")


def hidden(page):
    return page.eval_on_selector("#wt-changes", "el => el.hidden")


def test_hidden_until_something_changes(served):
    _, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        assert hidden(page) is True
        page.click("#headline")                 # selecting alone is not a change
        assert hidden(page) is True
        browser.close()


def test_counts_edited_elements_not_edits(served):
    """Two properties on one element is still one element changed."""
    _, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        edit(page, "#headline", "#wt-fs", "52")
        assert hidden(page) is False
        assert "1 element changed" in head(page)

        # "2px", not "2": #wt-ls declares no unit, so a bare number fails
        # CSS.supports and is rejected - the second property was never recorded and
        # this assertion merely restated the one above it.
        page.fill("#wt-ls", "2px")              # second property, same element
        page.dispatch_event("#wt-ls", "input")
        assert "1 element changed" in head(page)

        edit(page, ".lede", "#wt-fs", "19")    # a second element
        assert "2 elements changed" in head(page)
        browser.close()


def test_expanding_lists_each_element_and_its_props(served):
    _, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        edit(page, "#headline", "#wt-fs", "52")
        page.click("#wt-changes-head")
        page.wait_for_selector("#wt-changes-list:not([hidden])")
        rows = page.eval_on_selector_all(".wt-change", "els => els.map(e => e.textContent)")
        assert len(rows) == 1
        assert "h1#headline" in rows[0]
        assert "font-size" in rows[0]
        browser.close()


def test_clicking_an_entry_selects_that_element(served):
    _, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        edit(page, "#headline", "#wt-fs", "52")
        edit(page, ".lede", "#wt-fs", "19")
        page.click("#wt-changes-head")
        page.wait_for_selector("#wt-changes-list:not([hidden])")
        assert selected(page) == "p.lede"

        page.click(".wt-change:has-text('h1#headline')")
        assert selected(page) == "h1#headline"
        browser.close()


def test_undo_and_reset_shrink_the_list(served):
    """A stale count would make the list actively misleading at exactly the
    moment it is meant to build confidence - just before Save."""
    _, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        edit(page, "#headline", "#wt-fs", "52")
        edit(page, ".lede", "#wt-fs", "19")
        assert "2 elements changed" in head(page)

        page.keyboard.press("Control+z")        # undo the lede edit
        assert "1 element changed" in head(page)

        page.click("#headline")
        page.click("#wt-reset")
        assert hidden(page) is True             # nothing left to show
        browser.close()


def test_survives_a_reload_via_restore(served):
    """Saved edits come back through restore(), and the list must come back with
    them or it under-reports the session."""
    _, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        edit(page, "#headline", "#wt-fs", "52")
        page.click("#wt-save")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.startsWith('saved')")
        page.reload()
        page.wait_for_selector("#wt-root")
        page.wait_for_function(
            "!document.getElementById('wt-changes').hidden", timeout=8000)
        assert "1 element changed" in head(page)
        browser.close()
