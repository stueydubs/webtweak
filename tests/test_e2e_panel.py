"""Browser end-to-end test of collapsible groups and the per-field revert.

Two navigation problems, not styling ones. The panel is ~780px of content and scrolls
on any window shorter than about 800px, so a group you are not using costs you the
one you are. And undoing a single property meant knowing to clear its field, which
nothing on screen suggests - Reset discards the whole element instead.
"""

from conftest import changes, open_page, save, select_card, set_field, revert_shown

from _browser import sync_playwright, pytestmark  # noqa: F401


def group_open(page, group="Type"):
    return page.evaluate(
        """g => {
            const node = document.querySelector(`#wt-panel .wt-group[data-group="${g}"]`);
            return {
                bodyShown: !node.querySelector('.wt-group-body').hidden,
                legendShown: !!node.querySelector('.wt-legend').offsetParent,
                expanded: node.querySelector('.wt-legend').getAttribute('aria-expanded'),
            };
        }""",
        group,
    )


def test_a_group_collapses_and_keeps_its_legend(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        before = group_open(page, "Type")
        page.click('#wt-panel .wt-group[data-group="Type"] .wt-legend')
        after = group_open(page, "Type")
        browser.close()
    assert before == {"bodyShown": True, "legendShown": True, "expanded": "true"}
    # the fields go, the legend stays - otherwise you could not get them back
    assert after == {"bodyShown": False, "legendShown": True, "expanded": "false"}


def test_a_collapsed_group_stays_collapsed_across_selections(served):
    """State belongs to the panel, not to the element - collapsing Type once should
    not have to be redone on every click."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        page.click('#wt-panel .wt-group[data-group="Box"] .wt-legend')
        select_card(page)
        after_reselect = group_open(page, "Box")
        page.click('#wt-panel .wt-group[data-group="Box"] .wt-legend')
        reopened = group_open(page, "Box")
        browser.close()
    assert after_reselect["bodyShown"] is False
    assert reopened["bodyShown"] is True


def test_collapsing_does_not_disturb_the_shape_group_rules(served):
    """Group visibility (Shape hidden for elements) and collapse are separate axes:
    collapsing Box must not make Shape appear for a non-shape."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        page.click('#wt-panel .wt-group[data-group="Box"] .wt-legend')
        shape_hidden = page.eval_on_selector(
            '#wt-panel .wt-group[data-group="Shape"]', "el => el.hidden")
        browser.close()
    assert shape_hidden is True


def test_the_revert_mark_appears_only_for_an_edited_property(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        before = revert_shown(page, "wt-fs")
        set_field(page, "#wt-fs", "52px")
        after = revert_shown(page, "wt-fs")
        untouched = revert_shown(page, "wt-lh")
        browser.close()
    assert before is False
    assert after is True
    assert untouched is False       # only the property you changed is marked


def test_clicking_the_revert_mark_undoes_just_that_property(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        set_field(page, "#wt-fs", "52px")
        set_field(page, "#wt-ls", "0.05em")
        page.click("#wt-fs-revert")
        size = page.eval_on_selector("#headline", "el => getComputedStyle(el).fontSize")
        spacing = page.eval_on_selector("#headline", "el => getComputedStyle(el).letterSpacing")
        gone = revert_shown(page, "wt-fs")
        save(page)
        browser.close()
    assert size == "44px"                              # back to the authored size
    assert spacing != "normal"                         # the other edit is untouched
    assert gone is False                               # and the mark went with it
    assert changes(tmp) == {"letter-spacing": "0.05em"}


def test_the_revert_mark_covers_a_per_side_row(served):
    """A sides row holds up to five recorded properties, so its mark reverts the row -
    which is what a user means by "undo what I did to padding"."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        set_field(page, "#wt-padding-top", "40px")
        set_field(page, "#wt-padding-left", "8px")
        marked = revert_shown(page, "wt-padding")
        page.click("#wt-padding-revert")
        rendered = page.evaluate(
            """() => { const cs = getComputedStyle(document.querySelector('.card'));
                return ['Top','Right','Bottom','Left'].map(s => cs['padding' + s]); }"""
        )
        page.click("#wt-save")
        status = page.eval_on_selector("#wt-status", "el => el.textContent")
        browser.close()
    assert marked is True
    assert rendered == ["24px"] * 4
    assert status == "nothing changed yet"


def test_reverting_a_property_is_undoable(served):
    """It goes through the same history as any other change."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        set_field(page, "#wt-fs", "52px")
        page.click("#wt-fs-revert")
        reverted = page.eval_on_selector("#headline", "el => getComputedStyle(el).fontSize")
        page.keyboard.press("Control+z")
        back = page.eval_on_selector("#headline", "el => getComputedStyle(el).fontSize")
        browser.close()
    assert reverted == "44px"
    assert back == "52px"
