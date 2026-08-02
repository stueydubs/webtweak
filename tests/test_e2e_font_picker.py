"""Browser end-to-end test of the Font control's suggestion list.

The Font control is a text input backed by a list of the Target page's own font
stacks, so a restyle keeps the fallbacks the page's author intended instead of
depending on the user retyping them. Driven the way a user drives it - open the
list, click an entry, save - and asserted on the rendered page and the Patches.
"""

from conftest import changes, open_page, save, selected

from _browser import sync_playwright, pytestmark  # noqa: F401

BODY_STACK = 'Georgia, "Times New Roman", serif'   # fixture body
EYEBROW_STACK = "system-ui, sans-serif"            # fixture .eyebrow
FACE_FAMILY = "Fixture Display"                    # fixture @font-face, applied nowhere


def suggestions(page, selector="#headline"):
    """Select an element, open the Font control's list, return its entries."""
    page.click(selector)
    page.click("#wt-ff-toggle")
    return page.eval_on_selector_all(
        "#wt-ff-list .wt-suggest-item", "els => els.map(e => e.dataset.value)"
    )


def font_patch(tmp):
    """The one saved patch's font-family value (None if it recorded none)."""
    return changes(tmp).get("font-family")


def test_suggestions_offer_the_pages_own_stacks(served):
    """Every distinct stack in use on the page is offered, as authored - full
    stack, so picking one cannot drop a fallback.

    Asserted as the exact set: the interesting failures are extra entries, not
    missing ones. The browser's UA default for <html> ("Times New Roman", which no
    element of the page asks for) is exactly the kind of noise that would otherwise
    ride along unnoticed on every page.
    """
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        entries = suggestions(page)
        # each row renders in the face it offers, so a font is picked by its look
        rendered = page.eval_on_selector_all(
            "#wt-ff-list .wt-suggest-item",
            "els => els.every(e => getComputedStyle(e).fontFamily === e.dataset.value)")
        browser.close()
    assert rendered
    assert entries == [
        BODY_STACK,          # body
        EYEBROW_STACK,       # .eyebrow
        "monospace",         # the UA default for the <code> element - genuinely in use
        f'"{FACE_FAMILY}"',  # declared @font-face, applied nowhere
    ]


def test_a_declared_font_face_family_is_pickable(served):
    """A self-hosted face declared but not yet applied anywhere is one click away -
    and picking it records, so being offered is not where it stops."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        page.click("#wt-ff-toggle")
        page.click(f"#wt-ff-list .wt-suggest-item[data-value='\"{FACE_FAMILY}\"']")
        save(page)
        browser.close()
    assert font_patch(tmp) == f'"{FACE_FAMILY}"'


def test_suggestions_exclude_the_overlays_own_fonts(served):
    """The suggestions are the page's vocabulary, not the editor's.

    The Overlay's own interface font is read off the live panel rather than
    hardcoded, so this keeps testing the right thing if the editor is restyled.
    """
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        entries = suggestions(page)
        own = page.eval_on_selector("#wt-panel", "el => getComputedStyle(el).fontFamily")
        field = page.eval_on_selector("#wt-ff", "el => getComputedStyle(el).fontFamily")
        browser.close()
    assert own and own not in entries, f"the Overlay's {own} leaked into {entries}"
    assert field and field not in entries      # its monospace fields too


def test_unreadable_stylesheet_degrades_the_list(served):
    """The common case - a page whose display face comes from a hosted webfont -
    must leave the list populated from computed style rather than throwing.

    The unreadable sheet is real, not stubbed: the same server answers on
    localhost as well as 127.0.0.1, and that hostname difference is a different
    origin, so reading its rules raises the same SecurityError a CDN sheet does.
    """
    tmp, port = served
    (tmp / "hosted.css").write_text(
        '@font-face { font-family: "Hidden Face"; src: local("Hidden Face"); }\n'
    )
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        loaded = page.evaluate(
            """port => new Promise(res => {
                const l = document.createElement('link');
                l.rel = 'stylesheet';
                l.href = 'http://localhost:' + port + '/hosted.css';
                l.onload = () => res(true);
                l.onerror = () => res(false);
                document.head.appendChild(l);
            })""",
            port,
        )
        # The premise of the test: that sheet really is unreadable.
        errs = page.evaluate(
            """() => Array.from(document.styleSheets)
                .filter(s => (s.href || '').includes('hosted.css'))
                .map(s => { try { s.cssRules.length; return null; } catch (e) { return e.name; } })"""
        )
        entries = suggestions(page)
        browser.close()
    assert loaded and errs == ["SecurityError"], errs
    assert BODY_STACK in entries                      # degraded, not thrown
    assert not any("Hidden Face" in e for e in entries)


def test_picking_a_suggestion_records_the_complete_stack(served):
    """Clicking an entry writes that stack verbatim into the Patch, fallbacks intact."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click(".eyebrow")
        page.click("#wt-ff-toggle")
        # single-quoted: the stack itself contains the double quotes around a family
        page.click(f"#wt-ff-list .wt-suggest-item[data-value='{BODY_STACK}']")
        shown = page.eval_on_selector(".eyebrow", "el => getComputedStyle(el).fontFamily")
        field = page.eval_on_selector("#wt-ff", "el => el.value")
        save(page)
        browser.close()
    assert shown == BODY_STACK       # what the user saw
    assert field == BODY_STACK       # ... and what the control now reads
    assert font_patch(tmp) == BODY_STACK


def test_the_list_closes_without_losing_the_selection(served):
    """An open list hangs over the fields beneath it, so it has to close on Esc and
    on a click elsewhere - and Esc must dismiss the list, not the selection behind it.
    """
    tmp, port = served
    open_list = "#wt-ff-list:not([hidden])"
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        page.click("#wt-ff-toggle")
        page.wait_for_selector(open_list)
        page.keyboard.press("Escape")
        page.wait_for_selector(open_list, state="hidden")
        assert selected(page) == "h1#headline"

        page.click("#wt-ff-toggle")                 # reopen, then click the page
        page.wait_for_selector(open_list)
        page.click(".lede")
        page.wait_for_selector(open_list, state="hidden")
        assert selected(page) == "p.lede"
        browser.close()


def test_typed_arbitrary_stack_still_records(served):
    """The list is a suggestion, not a closed set: a font being introduced for the
    first time cannot be blocked by a list that can't know about it."""
    tmp, port = served
    typed = "Futura, Impact, sans-serif"
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        page.fill("#wt-ff", typed)
        page.dispatch_event("#wt-ff", "input")
        save(page)
        browser.close()
    assert font_patch(tmp) == typed


def test_typed_invalid_font_records_nothing(served):
    """A stray comma while typing a stack is rejected by the browser, so it never
    previewed - and must not become a Patch either."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        page.fill("#wt-ff", "Georgia, , serif")     # invalid - the browser drops it
        page.dispatch_event("#wt-ff", "input")
        status = page.eval_on_selector("#wt-status", "el => el.textContent")
        page.fill("#wt-fs", "52")                   # a real edit, so there is a batch
        page.dispatch_event("#wt-fs", "input")
        save(page)
        browser.close()
    assert status.startswith("ignored invalid font-family")
    assert font_patch(tmp) is None
