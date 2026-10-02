"""Browser e2e for the Overlay's accessibility surface (issue #56): live regions,
control names, the shape palette's open state and selected state.

Every assertion here reads the DOM the way assistive tech does - roles, aria-*
attributes and Playwright's role/label locators - rather than the colours and classes
a sighted user sees, because the colours and classes were all that existed before.
"""

from conftest import edit, open_page, save

from _browser import sync_playwright, pytestmark  # noqa: F401

LIVE = ("polite", "assertive")


def live_attr(page, selector):
    """The role and aria-live of the element, and of every ancestor up to the root."""
    return page.evaluate(
        """sel => {
            const out = [];
            for (let el = document.querySelector(sel); el; el = el.parentElement) {
                out.push([el.getAttribute('role'), el.getAttribute('aria-live')]);
            }
            return out;
        }""", selector)


def is_live(pairs):
    return any(r == "status" or l in LIVE for r, l in pairs)


# --- part 1: live regions ----------------------------------------------------------

def test_status_is_a_live_region_before_any_message(served):
    """A region added alongside its first message is not announced, so it has to be
    live from mount - before anything has been said."""
    _, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        assert page.eval_on_selector("#wt-status", "el => el.textContent") == ""
        assert is_live(live_attr(page, "#wt-status"))
        browser.close()


def test_a_refused_scope_is_said_in_the_live_region(served):
    _, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.fill("#wt-scope-input", "garbage")
        page.dispatch_event("#wt-scope-input", "change")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.includes('not a media condition')")
        assert is_live(live_attr(page, "#wt-status"))
        assert "not a media condition" in page.text_content("#wt-status")
        browser.close()


def test_the_badge_text_change_on_save_is_in_a_live_region(served):
    _, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        assert is_live(live_attr(page, "#wt-badge-live"))
        assert page.eval_on_selector("#wt-badge-live", "el => el.textContent") == ""
        edit(page, "#headline", "#wt-fs", "40")
        save(page)
        page.wait_for_function(
            "document.getElementById('wt-badge').textContent.trim() !== ''")
        shown = page.text_content("#wt-badge").strip()
        # The mirror says what the badge says, and the region it is in is live.
        assert page.text_content("#wt-badge-live").strip() == shown
        assert is_live(live_attr(page, "#wt-badge-live"))
        browser.close()


# --- part 2: names -----------------------------------------------------------------

def select_paragraph(page):
    page.click("p.lede")
    page.wait_for_selector("#wt-panel:not([hidden])")


def accessible_names(page, selector):
    return page.evaluate(
        """sel => Array.from(document.querySelectorAll(sel)).map(el =>
            el.getAttribute('aria-label') || el.title ||
            (el.labels && el.labels.length ? el.labels[0].textContent : '') ||
            el.textContent.trim())""", selector)


def test_every_panel_control_has_a_unique_name(served):
    _, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_paragraph(page)
        names = accessible_names(page, "#wt-panel input, #wt-panel select, #wt-panel textarea")
        assert len(names) > 25, "the panel shrank, or the selector stopped matching"
        assert all(names), names
        assert len(set(names)) == len(names), sorted(names)
        # Shape-only controls are in the panel markup whether or not they are shown.
        panel = page.locator("#wt-panel")
        assert panel.get_by_label("Border Width").count() == 1
        assert panel.get_by_label("Box Width").count() == 1
        browser.close()


def test_a_declined_control_keeps_its_property_as_its_name(served):
    """A decline rule puts a tooltip on the control, and the title becomes the name when
    nothing else names it. aria-label has to win."""
    _, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_paragraph(page)
        page.evaluate("document.getElementById('wt-w').title = 'width/height are ignored'")
        assert page.locator("#wt-panel").get_by_role(
            "textbox", name="Box Width", exact=True).count() == 1
        browser.close()


def test_repeated_buttons_name_their_property(served):
    _, port = served
    generic = {"Increase", "Decrease", "Undo this property", "Suggestions",
               "Link all four sides"}
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_paragraph(page)
        for sel in ("#wt-panel .wt-revert", "#wt-panel .wt-step-btns button",
                    "#wt-panel .wt-suggest-toggle", "#wt-panel .wt-link"):
            names = accessible_names(page, sel)
            assert names, sel
            assert not generic & set(names), (sel, names)
            assert len(set(names)) == len(names), (sel, names)
        assert page.locator("#wt-panel").get_by_role(
            "button", name="Increase Width").count() == 1
        assert page.locator("#wt-panel").get_by_role(
            "button", name="Link all Margin sides").count() == 1
        browser.close()


# --- part 3: the shape palette -----------------------------------------------------

def expanded(page):
    return page.get_attribute("#wt-shape-btn", "aria-expanded")


def palette_open(page):
    page.click("#wt-shape-btn")
    assert expanded(page) == "true"
    assert page.eval_on_selector("#wt-palette", "el => el.hidden") is False


def test_palette_state_follows_every_way_it_closes(served):
    _, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        assert expanded(page) == "false"

        palette_open(page)
        page.click("#wt-shape-btn")                       # second click
        assert expanded(page) == "false"

        palette_open(page)
        page.keyboard.press("Escape")
        assert expanded(page) == "false"

        palette_open(page)
        page.mouse.click(600, 600)                        # a page click
        assert expanded(page) == "false"

        palette_open(page)
        page.click('.wt-shape-item[data-shape="square"]')  # enters place mode
        assert expanded(page) == "false"
        assert page.eval_on_selector("#wt-palette", "el => el.hidden") is True
        browser.close()


def test_palette_state_follows_peek(served):
    _, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        palette_open(page)
        page.keyboard.press("h")
        page.wait_for_function(
            "document.getElementById('wt-root').classList.contains('wt-peek')")
        assert expanded(page) == "false"
        browser.close()


def test_palette_items_are_named_by_shape(served):
    _, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        palette_open(page)
        kinds = page.eval_on_selector_all(
            ".wt-shape-item", "els => els.map(e => e.dataset.shape)")
        assert len(kinds) >= 5
        for kind in kinds:
            name = kind[0].upper() + kind[1:]
            assert page.get_by_role("button", name=name, exact=True).count() == 1, name
        assert page.eval_on_selector_all(
            ".wt-shape-item svg", "els => els.map(e => e.getAttribute('aria-hidden'))"
        ) == ["true"] * len(kinds)
        assert page.get_attribute("#wt-shape-btn", "aria-controls") == "wt-palette"
        assert page.get_attribute("#wt-palette", "role") == "group"
        assert page.get_attribute("#wt-palette", "aria-label") == "Shapes"
        browser.close()


# --- part 4: selected state --------------------------------------------------------

def test_the_chosen_alignment_is_pressed(served):
    _, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        select_paragraph(page)
        assert page.get_attribute("#wt-align", "role") == "group"
        page.click('#wt-align [data-align="center"]')
        pressed = page.eval_on_selector_all(
            "#wt-align button",
            "els => Object.fromEntries(els.map(e => [e.dataset.align, e.getAttribute('aria-pressed')]))")
        assert pressed == {"left": "false", "center": "true",
                           "right": "false", "justify": "false"}
        assert page.locator("[data-align=center][aria-pressed=true]").count() == 1
        # Reselecting repaints from the element, not from the last click. The headline
        # is not centred, so a repaint that left Centre pressed would still count one.
        page.click("#headline")
        state = page.eval_on_selector_all(
            "#wt-align button",
            "els => els.map(e => [e.dataset.align, e.getAttribute('aria-pressed'),"
            " e.classList.contains('on')])")
        pressed = [a for a, p, _ in state if p == "true"]
        assert len(pressed) == 1 and pressed != ["center"], state
        assert all((p == "true") == on for _, p, on in state), state
        browser.close()


def test_the_selected_change_row_is_current(served):
    _, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        edit(page, "#headline", "#wt-fs", "40")
        edit(page, "p.lede", "#wt-fs", "22")
        page.click("#wt-changes-head")
        rows = page.locator(".wt-change")
        assert rows.count() == 2
        page.click("#headline")
        current = page.eval_on_selector_all(
            ".wt-change", "els => els.map(e => e.getAttribute('aria-current'))")
        assert current.count("true") == 1 and len(current) == 2, current
        assert page.locator(".wt-change.on[aria-current=true]").count() == 1
        page.click("#wt-deselect")
        assert page.locator(".wt-change[aria-current]").count() == 0
        browser.close()
