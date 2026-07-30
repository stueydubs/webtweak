"""Browser end-to-end test of breakpoint discovery and the band picker (issue 0014).

The Overlay learns which breakpoints the Target page declares and lets the user say
which one they are editing. Nothing is recorded differently yet - this is the target
selector issue 0015 writes through - so every assertion here is about what the picker
DISCOVERS, what it OFFERS, and what it SAYS the scope is.

Two rules carry most of the weight, and both come from driving a real browser rather
than reasoning about one:

  * Several bands match at once. At a 480px window the fixture's `(max-width: 900px)`
    and `(max-width: 600px)` both apply, so "the current breakpoint" is not a single
    thing and the default has to be the narrowest match, shown at all times.
  * A band the window is not inside is listed but NOT selectable. `getComputedStyle`
    at 1280px cannot see a 600px-only declaration, so the panel would fight the user
    and - worse - record a change the page never showed.
"""

from conftest import open_page, patches, save, set_field

from _browser import sync_playwright, pytestmark  # noqa: F401

BASE = "all widths"


def scope_shown(page):
    """What the bar says the scope is, without opening the picker."""
    return page.eval_on_selector("#wt-scope-input", "el => el.value")


def resize(page, width):
    """Resize the window and let the page actually observe it.

    `set_viewport_size` resolves before Chromium has necessarily dispatched the
    resize and media-query-change tasks, so reading the scope straight afterwards
    raced them and failed about one run in five. Waiting for `innerWidth` and then
    firing one more resize mirrors what a real drag does - it sends a stream of them,
    not a single event - rather than papering over the timing with a fixed pause.
    """
    page.set_viewport_size({"width": width, "height": 900})
    page.wait_for_function("w => window.innerWidth === w", arg=width)
    page.evaluate("() => window.dispatchEvent(new Event('resize'))")


def bands(page, reopen=True):
    """Open the picker and read every row it offers.

    Entries are rebuilt on every open (the font picker's precedent), so `reopen`
    lets a test re-read the list after changing the window.
    """
    if reopen:
        page.click("#wt-scope-toggle")
    rows = page.evaluate(
        """() => Array.from(document.querySelectorAll('#wt-scope-list .wt-band'))
            .map(b => ({
                condition: b.dataset.condition,
                state: b.dataset.state,
                label: b.querySelector('.wt-band-label').textContent,
                cond: b.querySelector('.wt-band-cond').textContent,
                note: b.querySelector('.wt-band-note').textContent,
                disabled: b.disabled,
            }))"""
    )
    if reopen:
        page.click("#wt-scope-toggle")   # leave it closed for the next assertion
    return rows


def band(page, condition, **kw):
    """One row by its condition text."""
    for row in bands(page, **kw):
        if row["condition"] == condition:
            return row
    raise AssertionError(f"no band row for {condition!r}")


def pick(page, condition):
    """Click a row the way a user does."""
    page.click("#wt-scope-toggle")
    page.click(f'#wt-scope-list .wt-band[data-condition="{condition}"]')


def test_the_picker_lists_the_pages_own_width_queries(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        offered = [r["condition"] for r in bands(page)]
        browser.close()
    # Both of the fixture's width bands, and base as an explicit choice rather than
    # an implicit default you cannot get back to.
    assert "" in offered
    assert "(max-width: 900px)" in offered
    assert "(max-width: 600px)" in offered


def test_the_bar_reads_as_a_scope_never_as_the_editing_subject(served):
    """A mock labelled `Editing: (max-width: 480px)` read as though the media query
    were the thing being edited. The element is the subject; the band is the
    condition - so the control says where an edit applies, and nothing else."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        bar = page.eval_on_selector(".wt-bar", "el => el.textContent")
        label = page.eval_on_selector("#wt-scope .wt-scope-label", "el => el.textContent")
        browser.close()
    assert "Applies at" in label
    assert "Editing" not in bar


def test_the_scope_stays_labelled_on_a_narrow_window(served):
    """The label is shortened at narrow widths, never dropped. Hiding it left a bare
    `≤600px` beside a caret at 480px - which is the width this feature exists to be
    used at, so it is the one width where the control most needs to say what it is."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        label = page.eval_on_selector("#wt-scope .wt-scope-label", "el => el.innerText.trim()")
        browser.close()
    assert label == "At:"


def test_the_crumb_names_the_element_and_the_panel_states_both(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        crumb = page.eval_on_selector("#wt-crumb", "el => el.textContent")
        note = page.eval_on_selector("#wt-scope-note", "el => el.textContent")
        browser.close()
    # describe() names an element by its id when it has one, so the headline reads
    # h1#headline - the same string the crumb and the selection tag already use.
    assert "h1#headline" in crumb            # the breadcrumb still names the object
    assert note == f"h1#headline at {BASE}"  # ...and the panel states object AND scope


def test_the_bar_shows_a_readable_form_and_the_picker_the_real_condition(served):
    tmp, port = served
    with sync_playwright() as p:
        # Opened narrow rather than resized into it, deliberately. Widening out of a
        # band drops the scope outward, but narrowing does NOT pull it in: base is a
        # choice ("this is wrong everywhere"), and quietly turning it into a banded
        # scope because the window moved is the silent inference this design refuses.
        browser, page = open_page(p, port, width=480)
        shown = scope_shown(page)
        row = band(page, "(max-width: 600px)")
        browser.close()
    assert shown == "≤600px"                       # readable, in the bar
    assert row["label"] == "≤600px"
    assert row["cond"] == "(max-width: 600px)"     # verbatim, in the picker


def test_matching_bands_are_marked_at_each_width(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        wide = {r["condition"]: r["state"] for r in bands(page)}
        resize(page, 700)
        mid = {r["condition"]: r["state"] for r in bands(page)}
        resize(page, 480)
        narrow = {r["condition"]: r["state"] for r in bands(page)}
        browser.close()
    # 1280: neither width band applies. 700: only the 900. 480: both - which is the
    # whole reason the scope is chosen rather than inferred.
    assert wide["(max-width: 900px)"] == "elsewhere"
    assert wide["(max-width: 600px)"] == "elsewhere"
    assert mid["(max-width: 900px)"] == "matching"
    assert mid["(max-width: 600px)"] == "elsewhere"
    assert narrow["(max-width: 900px)"] == "matching"
    assert narrow["(max-width: 600px)"] == "matching"
    assert narrow[""] == "matching"      # base always applies


def test_the_default_scope_is_the_narrowest_matching_band(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        narrow = scope_shown(page)
        browser.close()
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=1280)
        wide = scope_shown(page)
        browser.close()
    # Someone who has just dragged their window narrow is thinking about the most
    # specific band, not the widest one that happens to match.
    assert narrow == "≤600px"
    assert wide == BASE


def test_base_is_selectable_while_a_narrow_band_matches(served):
    """"This is wrong everywhere and I happened to notice it on mobile" is a real
    edit, so base has to be reachable at any width."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        assert scope_shown(page) == "≤600px"
        pick(page, "")
        shown = scope_shown(page)
        browser.close()
    assert shown == BASE


def test_a_band_the_window_is_not_inside_is_listed_but_not_selectable(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=1280)
        row = band(page, "(max-width: 600px)")
        # Clicking it must not change the scope - the guard is on the control, not
        # merely on its styling.
        page.click("#wt-scope-toggle")
        page.click('#wt-scope-list .wt-band[data-condition="(max-width: 600px)"]', force=True)
        after = scope_shown(page)
        browser.close()
    assert row["disabled"] is True
    assert row["note"] == "resize under 600px"   # says how to reach it
    assert after == BASE


def test_dragging_out_of_the_band_moves_the_scope(served):
    """The bar shows the scope at all times, so this is observable rather than
    silent - the alternative is authoring into a band you have left."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        assert scope_shown(page) == "≤600px"
        resize(page, 700)
        mid = scope_shown(page)
        resize(page, 1280)
        wide = scope_shown(page)
        browser.close()
    assert mid == "≤900px"     # narrowest band that still matches
    assert wide == BASE        # ...ending at base


def test_narrowing_the_window_does_not_pull_the_scope_into_a_band(served):
    """The other half of the rule above, and the half that is easy to get wrong.
    Widening out of a band moves the scope outward because the band can no longer be
    previewed. Narrowing INTO one carries no such force: base was chosen, and quietly
    converting it to a banded scope would silently re-aim every subsequent edit."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=1280)
        assert scope_shown(page) == BASE
        resize(page, 480)
        shown = scope_shown(page)
        browser.close()
    assert shown == BASE


def test_a_non_width_query_is_listed_as_unavailable_with_a_reason(served):
    """Same rule as a band the window is not inside, reached from the other side:
    `print` cannot be previewed by resizing, so an edit against it would record a
    change the user was never shown. Declined out loud, following the mixed-side
    border guard."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        row = band(page, "print")
        browser.close()
    assert row["state"] == "unavailable"
    assert row["disabled"] is True
    assert "cannot be previewed by resizing" in row["note"]


def test_webtweaks_own_media_queries_are_not_offered_as_the_pages(served):
    """The Overlay's stylesheet has breakpoints of its own (the bar collapses on a
    narrow window). Offering them would be the editor describing itself."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        offered = [r["cond"] for r in bands(page)]
        own = page.evaluate(
            """() => {
                const sheet = Array.from(document.styleSheets)
                    .find(s => (s.href || '').includes('/__webtweak__/overlay.css'));
                return Array.from(sheet.cssRules)
                    .filter(r => r.media)
                    .map(r => r.conditionText);
            }"""
        )
        browser.close()
    assert own, "the overlay stylesheet should declare at least one media query"
    for condition in own:
        assert condition not in offered


def test_a_nested_media_rule_is_offered_joined_to_its_parent(served):
    """A nested condition only applies WITHIN its parent's, so the two are one band.
    Offering the inner half alone would hand issue 0015 a condition to write that is
    broader than anything the page declares - a `(max-width: 500px)` block that also
    governed print, from a page that only ever said it for screen."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        page.evaluate(
            """() => {
                const sheet = Array.from(document.styleSheets)
                    .find(s => !(s.href || '').includes('/__webtweak__/'));
                sheet.insertRule(
                    '@media screen { @media (max-width: 500px) { .lede { color: red } } }',
                    sheet.cssRules.length);
            }"""
        )
        offered = [r["condition"] for r in bands(page)]
        browser.close()
    assert "screen and (max-width: 500px)" in offered
    assert "(max-width: 500px)" not in offered   # never the inner half on its own


def test_an_unreadable_stylesheet_leaves_the_list_populated(served):
    """A CDN-hosted sheet raises SecurityError on cssRules. Gathered the way
    @font-face families are - in a try/catch - so it degrades the list instead of
    throwing and taking the whole picker with it."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.route(
            "https://cdn.example.com/**",
            lambda route: route.fulfill(
                status=200,
                content_type="text/css",
                body="@media (max-width: 320px) { body { color: red } }",
            ),
        )
        page.evaluate(
            """() => new Promise(resolve => {
                const link = document.createElement('link');
                link.rel = 'stylesheet';
                link.href = 'https://cdn.example.com/fonts.css';
                link.onload = link.onerror = resolve;
                document.head.appendChild(link);
            })"""
        )
        # The cross-origin sheet really is unreadable, or this test proves nothing.
        blocked = page.evaluate(
            """() => {
                const sheet = Array.from(document.styleSheets)
                    .find(s => (s.href || '').includes('cdn.example.com'));
                try { return sheet.cssRules === null; } catch (e) { return true; }
            }"""
        )
        offered = [r["condition"] for r in bands(page)]
        browser.close()
    assert blocked is True
    assert "(max-width: 900px)" in offered      # the readable sheet still contributes
    assert "(max-width: 320px)" not in offered  # the unreadable one simply cannot


def test_a_page_with_no_media_queries_offers_base_plus_manual_entry(served):
    tmp, port = served
    with sync_playwright() as p:
        # Narrow, so the manual condition below is one this window is actually
        # inside - typing a band you cannot see is refused, and rightly.
        browser, page = open_page(p, port, width=480)
        # Strip the fixture's own queries, so this is a page that declares none.
        page.evaluate(
            """() => {
                const sheet = Array.from(document.styleSheets)
                    .find(s => !(s.href || '').includes('/__webtweak__/'));
                for (let i = sheet.cssRules.length - 1; i >= 0; i--) {
                    if (sheet.cssRules[i].media) sheet.deleteRule(i);
                }
            }"""
        )
        rows = bands(page)
        # Manual entry is the way out: the list is a convenience, never a gate.
        page.fill("#wt-scope-input", "(max-width: 500px)")
        page.dispatch_event("#wt-scope-input", "change")
        after = scope_shown(page)
        browser.close()
    assert [r["condition"] for r in rows] == [""]     # base, and nothing to discover
    assert after == "≤500px"


def test_a_manually_typed_condition_becomes_the_scope(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        page.fill("#wt-scope-input", "(max-width: 520px)")
        page.dispatch_event("#wt-scope-input", "change")
        shown = scope_shown(page)
        listed = [r["condition"] for r in bands(page)]
        browser.close()
    assert shown == "≤520px"
    # It joins the list, so it can be returned to after picking something else.
    assert "(max-width: 520px)" in listed


def test_a_manual_condition_the_window_is_outside_is_declined(served):
    """The same guard as a listed band, applied to the typed path - otherwise manual
    entry is a hole straight through it."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=1280)
        page.fill("#wt-scope-input", "(max-width: 400px)")
        page.dispatch_event("#wt-scope-input", "change")
        shown = scope_shown(page)
        status = page.eval_on_selector("#wt-status", "el => el.textContent")
        browser.close()
    assert shown == BASE                  # scope unchanged, and the field says so
    assert "resize under 400px" in status


def test_a_manual_condition_that_is_not_a_width_is_declined(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.fill("#wt-scope-input", "(prefers-color-scheme: dark)")
        page.dispatch_event("#wt-scope-input", "change")
        shown = scope_shown(page)
        status = page.eval_on_selector("#wt-status", "el => el.textContent")
        browser.close()
    assert shown == BASE
    assert "cannot be previewed by resizing" in status


def test_nonsense_typed_into_the_scope_field_is_refused(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.fill("#wt-scope-input", "banana")
        page.dispatch_event("#wt-scope-input", "change")
        shown = scope_shown(page)
        status = page.eval_on_selector("#wt-status", "el => el.textContent")
        browser.close()
    assert shown == BASE
    assert "not a media condition" in status


def test_the_scope_survives_selecting_another_element(served):
    """Scope is session state, like a collapsed group - not something to re-choose on
    every selection."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        pick(page, "")                       # deliberately base, against the default
        # Clicked near their left edge, not their centre: at a 480px window the
        # properties panel covers the middle of a full-width paragraph.
        page.click("#headline", position={"x": 8, "y": 8})
        page.click(".lede", position={"x": 8, "y": 8})
        shown = scope_shown(page)
        note = page.eval_on_selector("#wt-scope-note", "el => el.textContent")
        browser.close()
    assert shown == BASE
    assert note == f"p.lede at {BASE}"


def test_picking_a_band_does_not_yet_change_what_is_recorded(served):
    """Pins the transitional state deliberately, so it cannot be mistaken for done.

    This issue builds the target selector; issue 0015 makes edits preview and record
    against it. Until that lands, an edit made with a band selected is still a base
    change - which means THIS COMMIT MUST NOT SHIP ON ITS OWN: the bar would promise a
    scope the patch does not carry. When 0015 lands, this test is replaced by its
    opposite rather than deleted.
    """
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        assert scope_shown(page) == "≤600px"
        page.click("#headline", position={"x": 8, "y": 8})
        set_field(page, "#wt-fs", "30px")
        save(page)
        browser.close()
    patch = patches(tmp)[0]
    assert patch["changes"]["font-size"] == "30px"
    # Asserted on the PATCH, not on `changes`: ADR-0004 puts `media` beside `changes`
    # as a sibling key, never inside it - so checking `changes` would pass just as
    # happily once 0015 lands, and this pin would never fire when it is meant to.
    assert "media" not in patch


def test_the_panel_reads_the_bands_own_values_with_no_extra_machinery(served):
    """Not a picker assertion, but the claim the whole release rests on: computed
    style already resolves the page's own media queries at the current width, so the
    panel populates per band for free."""
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=1280)
        page.click("#headline")
        wide = page.eval_on_selector("#wt-fs", "el => el.value")
        resize(page, 480)
        page.click("#headline", position={"x": 8, "y": 8})   # clear of the panel
        narrow = page.eval_on_selector("#wt-fs", "el => el.value")
        browser.close()
    assert wide == "44px"
    assert narrow == "32px"
