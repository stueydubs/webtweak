"""Browser end-to-end test of units on Size, Width and Height.

They were `<input type="number">`, which means `2rem`, `80%` and `4ch` were not hard
to enter - they were *impossible*, so the panel quietly forced px onto layouts that
were authored fluid. They are now stepper text fields: a bare number still means px,
anything with a unit is passed through, and the arrows keep whatever unit they were
given. Same trap line-height had before 0.5.0, same fix.
"""

from conftest import changes, open_page, save, select_card, set_field

from _browser import sync_playwright, pytestmark  # noqa: F401


def test_the_fields_show_their_unit(served):
    """Previously a bare number beside a `px` label, which is why no other unit could
    ever be expressed."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        shown = page.evaluate(
            """() => ['wt-fs', 'wt-w', 'wt-h'].map(id => document.getElementById(id).value)"""
        )
        browser.close()
    assert shown[0] == "44px"                 # h1.title font-size
    assert shown[1].endswith("px") and shown[2].endswith("px")


def test_a_rem_font_size_applies_and_records(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        set_field(page, "#wt-fs", "2rem")
        rendered = page.eval_on_selector("#headline", "el => getComputedStyle(el).fontSize")
        save(page)
        browser.close()
    assert rendered == "32px"                 # 2rem against a 16px root
    assert changes(tmp) == {"font-size": "2rem"}    # recorded as authored, not resolved


def test_a_bare_number_still_means_px(served):
    """The common case must not get harder: typing 52 has always meant 52px."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        set_field(page, "#wt-fs", "52")
        rendered = page.eval_on_selector("#headline", "el => getComputedStyle(el).fontSize")
        save(page)
        browser.close()
    assert rendered == "52px"
    assert changes(tmp) == {"font-size": "52px"}


def test_a_percentage_width_applies_and_records(served):
    """The one that matters for real layouts: a fluid width was unreachable before."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        set_field(page, "#wt-w", "80%")
        save(page)
        browser.close()
    assert changes(tmp) == {"width": "80%"}


def test_the_stepper_keeps_the_unit_on_a_size(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        set_field(page, "#wt-fs", "2rem")
        page.click("#wt-fs-up")
        shown = page.eval_on_selector("#wt-fs", "el => el.value")
        save(page)
        browser.close()
    assert shown == "3rem"
    assert changes(tmp) == {"font-size": "3rem"}


def test_an_invalid_size_now_records_nothing(served):
    """A number input could not hold junk, so the invalid-value gate used to be skipped
    for these. Free text means the gate has to apply, or `banana` would record."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        set_field(page, "#wt-w", "banana")
        status = page.eval_on_selector("#wt-status", "el => el.textContent")
        page.click("#wt-save")
        saved = page.eval_on_selector("#wt-status", "el => el.textContent")
        browser.close()
    assert status.startswith("ignored invalid width")
    assert saved == "nothing changed yet"


def test_a_bare_zero_width_still_floors_to_one(served):
    """Existing behaviour, matching the resize grips: a 0px box cannot be grabbed."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_card(page)
        set_field(page, "#wt-w", "0")
        save(page)
        browser.close()
    assert changes(tmp) == {"width": "1px"}


def test_clearing_a_size_still_reverts(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        set_field(page, "#wt-fs", "2rem")
        set_field(page, "#wt-fs", "")
        rendered = page.eval_on_selector("#headline", "el => getComputedStyle(el).fontSize")
        page.click("#wt-save")
        status = page.eval_on_selector("#wt-status", "el => el.textContent")
        browser.close()
    assert rendered == "44px"
    assert status == "nothing changed yet"
