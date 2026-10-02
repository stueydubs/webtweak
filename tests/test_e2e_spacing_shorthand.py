"""Browser end-to-end test of a per-side spacing write while a shorthand is recorded.

Once a `padding` shorthand is recorded, deleting a side's longhand replays the
shorthand, so that side's baseline is the shorthand's value and not the authored
longhand. Comparing a typed side against the authored baseline treated "24px" as a
revert, deleted only the longhand, and left the side rendering the shorthand's 30px.
"""

from conftest import changes, open_page, save, select_card, set_field

from _browser import sync_playwright, pytestmark  # noqa: F401


def padding_of(page):
    return page.evaluate(
        """() => {
            const cs = getComputedStyle(document.querySelector('.card'));
            return ['Top','Right','Bottom','Left'].map(s => cs['padding' + s]);
        }"""
    )


def box(page, side):
    return page.evaluate("s => document.getElementById('wt-padding-' + s).value", side)


def record_unlinked_shorthand(page):
    """Link, write 30px (recorded as `padding`), then unlink for per-side edits."""
    page.click("#wt-padding-link")
    set_field(page, "#wt-padding-top", "30px")
    page.click("#wt-padding-link")


def test_typing_the_authored_baseline_over_a_shorthand_is_a_real_write(served):
    """.card is 24px padding. With `padding: 30px` recorded, typing 24px into the
    left box is a request for 24px there, so it must be recorded as the longhand."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        record_unlinked_shorthand(page)
        before = padding_of(page)
        set_field(page, "#wt-padding-left", "24px")
        rendered = padding_of(page)
        save(page)
        browser.close()
    assert before == ["30px"] * 4                 # guard: the shorthand really rendered
    assert rendered == ["30px", "30px", "30px", "24px"]
    assert changes(tmp) == {"padding": "30px", "padding-left": "24px"}


def test_typing_the_shorthand_value_records_nothing_extra(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        record_unlinked_shorthand(page)
        set_field(page, "#wt-padding-left", "8px")
        set_field(page, "#wt-padding-left", "30px")
        rendered = padding_of(page)
        save(page)
        browser.close()
    assert rendered == ["30px"] * 4
    assert changes(tmp) == {"padding": "30px"}


def test_clearing_a_side_over_a_shorthand_shows_the_shorthand(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        record_unlinked_shorthand(page)
        set_field(page, "#wt-padding-left", "8px")
        set_field(page, "#wt-padding-left", "")
        shown = box(page, "left")
        rendered = padding_of(page)
        save(page)
        browser.close()
    assert rendered == ["30px"] * 4
    assert shown == "30px"                        # not the authored 24px
    assert changes(tmp) == {"padding": "30px"}    # no stale longhand


def test_without_a_shorthand_typing_the_baseline_still_reverts(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        set_field(page, "#wt-padding-left", "8px")
        set_field(page, "#wt-padding-left", "24px")
        rendered = padding_of(page)
        page.click("#wt-save")
        saved = page.eval_on_selector("#wt-status", "el => el.textContent")
        browser.close()
    assert rendered == ["24px"] * 4
    assert saved == "nothing changed yet"
