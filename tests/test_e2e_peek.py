"""Browser end-to-end test of peek - hiding the Overlay so the page under it can be
reached (ADR-0005).

The defect this closes is not that the bar is tall. It is that anything under the
Overlay's chrome cannot be SELECTED, because the click lands on a control instead: a
page whose nav occupies its top 56px could not have that nav edited at any width,
including 1280px, where the click hits the Scope input. The panel and the dock do the
same to a right-hand rail and a bottom-left widget. Sampled with elementFromPoint on a
4px grid with an element selected, the chrome covers about 27% of a 1280x800 viewport
and about 76% of a 360x740 one.

So every test here comes in a pair - the region really does swallow the element, and
peek really does hand it back. A test that only proved the second half would still
pass if the collision fixture drifted out from under the chrome, which is precisely
how this would stop testing anything.
"""

from conftest import (centre, click_el, hit, open_page, selected,  # noqa: F401
                      served_collision, worst_case_bar)

from _browser import sync_playwright, pytestmark  # noqa: F401

PAGE = "chrome-collision.html"


def peeking(page):
    return page.evaluate(
        "document.getElementById('wt-root').classList.contains('wt-peek')")


def peek(page):
    page.keyboard.press("h")
    page.wait_for_function(
        "document.getElementById('wt-root').classList.contains('wt-peek')")


# --- the hole itself -------------------------------------------------------------

def test_top_nav_is_unreachable_at_every_width(served_collision):
    """The bar is 44px on one row and 90px wrapped, and the nav is under it in both
    states - so this is not a narrow-window problem to be waited out by maximising."""
    _, port = served_collision
    with sync_playwright() as pw:
        for width in (360, 480, 700, 1280):
            browser, page = open_page(pw, port, PAGE, width=width, height=800)
            assert hit(page, "#nav") == "chrome", f"nav not under the bar at {width}px"
            click_el(page, "#nav")
            assert selected(page) == "", f"nav selectable at {width}px without peek"
            browser.close()


def test_peek_reaches_the_top_nav(served_collision):
    _, port = served_collision
    with sync_playwright() as pw:
        for width in (360, 480, 700, 1280):
            browser, page = open_page(pw, port, PAGE, width=width, height=800)
            peek(page)
            assert hit(page, "#nav") == "page", f"chrome still hit-testing at {width}px"
            click_el(page, "#nav")
            # Pinned to exactly the nav. This was `in ("nav#nav", "a#nav-link")` on the
            # theory that the flexed links fill the bar's width at 360px - measured,
            # they do not: #nav-link spans x=18..64 at EVERY width, so the second
            # alternative was unreachable and only served to swallow a picker
            # regression that started selecting the deepest child.
            assert selected(page) == "nav#nav", \
                f"peek did not reach the nav at {width}px"
            browser.close()


def test_peek_reaches_content_under_the_panel(served_collision):
    """The panel is 270px of the right edge and only appears once something is
    selected, which is exactly when a user is trying to click the next thing."""
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=1280, height=900)
        click_el(page, "#headline")                 # open the panel
        assert selected(page) == "h1#headline"
        assert hit(page, "#rail") == "chrome"
        click_el(page, "#rail")
        assert selected(page) == "h1#headline", "rail selectable through the panel"
        # That click landed on a panel FIELD - the rail's centre is over the Width
        # input - so it took focus, and H is deliberately ignored while a field has
        # focus. Blur first, which is what clicking anywhere neutral would do. Worth
        # knowing rather than hiding: a user in this exact position presses H and
        # nothing happens, which is why setPeek's guarded branch now says so.
        page.evaluate("() => document.activeElement.blur()")
        peek(page)
        click_el(page, "#rail")
        assert selected(page) == "aside#rail"
        browser.close()


def test_peek_reaches_content_under_the_dock(served_collision):
    """The hint sits bottom-left whether or not anything is selected, so a page with
    its own corner widget collides with it from the moment the Overlay mounts."""
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=1280, height=900)
        assert hit(page, "#widget") == "chrome"
        click_el(page, "#widget")
        assert selected(page) == "", "widget selectable through the dock"
        peek(page)
        click_el(page, "#widget")
        assert selected(page) == "div#widget"
        browser.close()


def test_content_clear_of_the_chrome_never_needed_peek(served_collision):
    """The control case. If this ever fails, the fixture has drifted under the chrome
    and the pairs above stopped testing what they claim to."""
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=1280, height=900)
        assert hit(page, "#intro") == "page"
        click_el(page, "#intro")
        assert selected(page) == "p#intro"
        browser.close()


def test_the_key_is_discoverable_at_every_width(served_collision):
    """H is the only way to reach peek - there is no button for it - so the hint is the
    whole of its discoverability. The hint used to be `display: none` below 640px,
    which took the answer off the screen at exactly the widths where the chrome covers
    half the page and the question gets asked. `innerText` and not `textContent`: the
    long and short spellings are both in the DOM at every width, and only one of them
    is rendered."""
    _, port = served_collision
    with sync_playwright() as pw:
        for width in (1280, 700, 640, 620, 480, 360):
            browser, page = open_page(pw, port, PAGE, width=width, height=800)
            shown = page.eval_on_selector(
                ".wt-hint",
                """el => ({text: el.innerText,
                          h: Math.round(el.getBoundingClientRect().height),
                          display: getComputedStyle(el).display})""")
            assert shown["display"] != "none" and shown["h"] > 0, \
                f"the hint is not rendered at {width}px"
            assert "peek" in shown["text"].lower(), \
                f"nothing on screen mentions peek at {width}px: {shown['text']!r}"
            assert "H" in shown["text"], f"the key itself is unnamed at {width}px"
            # Exactly one spelling, and this half is what catches the cascade trap the
            # short defaults are gathered at the top of overlay.css to avoid. Losing
            # the base `.wt-hint-short { display: none }` does not hide the hint - it
            # renders BOTH sentences at wide widths, which still contains "peek" and
            # still has a height, so every assertion above stays green.
            spellings = page.eval_on_selector_all(
                ".wt-hint > span",
                "els => els.map(e => getComputedStyle(e).display).filter(d => d !== 'none')")
            assert len(spellings) == 1, \
                f"{len(spellings)} hint spellings rendered at once at {width}px"
            browser.close()


# --- the panel's share of the window ---------------------------------------------

def chrome_pct(page):
    """How much of the viewport the Overlay is on top of, sampled on a 4px grid.

    The area is the point of the bottom sheet, so the test measures it the same way the
    decision was made rather than asserting a box position and calling that a proxy.
    """
    return page.evaluate(
        """() => { const vw = innerWidth, vh = innerHeight; let hit = 0, total = 0;
             for (let y = 2; y < vh; y += 4) for (let x = 2; x < vw; x += 4) {
               total++;
               const e = document.elementFromPoint(x, y);
               if (e && e.closest('#wt-root')) hit++;
             }
             return 100 * hit / total; }"""
    )


def test_the_panel_is_a_bottom_sheet_below_the_crossover(served_collision):
    """A 270px column is 75% of a 360px window, and the 78px strip it leaves is too
    narrow to read a layout in. Below 520px the panel spans the width and sits on the
    bottom instead - full width and a bit over half the height."""
    _, port = served_collision
    with sync_playwright() as pw:
        for width in (520, 414, 360):
            browser, page = open_page(pw, port, PAGE, width=width, height=800)
            click_el(page, "#headline")
            box = page.eval_on_selector(
                ".wt-panel",
                """el => { const r = el.getBoundingClientRect();
                           return {l: Math.round(r.left), w: Math.round(r.width),
                                   b: Math.round(r.bottom), h: Math.round(r.height)}; }""")
            assert box["l"] == 0 and box["w"] == width, \
                f"the sheet does not span the window at {width}px: {box}"
            assert abs(box["b"] - 800) <= 1, f"the sheet is off the bottom at {width}px"
            assert box["h"] <= 800 * 0.45 + 1, f"the sheet is taller than 45vh at {width}px"
            browser.close()


def test_the_panel_is_still_a_column_above_the_crossover(served_collision):
    """The other side of the switch, and the reason it is at 520 rather than higher: a
    full-width sheet costs 45% of any window, while the column costs (270/w) x 0.89, so
    above the crossover the sheet would be the WORSE of the two. The first draft
    switched at 620px and made coverage there go up, from 46.7% to 55.7%."""
    _, port = served_collision
    with sync_playwright() as pw:
        for width in (560, 700, 1280):
            browser, page = open_page(pw, port, PAGE, width=width, height=800)
            click_el(page, "#headline")
            box = page.eval_on_selector(
                ".wt-panel",
                """el => { const r = el.getBoundingClientRect();
                           return {w: Math.round(r.width),
                                   right: Math.round(innerWidth - r.right)}; }""")
            assert box["w"] == 270, f"not a 270px column at {width}px: {box}"
            assert box["right"] == 12, f"column not against the right gutter at {width}px"
            browser.close()


def test_the_sheet_reduces_what_the_overlay_covers(served_collision):
    """The whole justification, asserted as the number it was argued from. Measured at
    360x740 the column layout covered 76.5% of the window; the sheet takes it to about
    64%. The bound is deliberately loose - this guards the direction and the order of
    magnitude, not a pixel count that would break on a font metric."""
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=360, height=740)
        click_el(page, "#headline")
        page.wait_for_selector("#wt-panel:not([hidden])")
        covered = chrome_pct(page)
        assert covered < 70, f"the Overlay covers {covered:.1f}% of a 360x740 window"
        peek(page)
        assert chrome_pct(page) == 0, "peek did not clear the sheet as well as the bar"
        browser.close()


def test_the_bar_gives_back_a_row_below_460px(served_collision):
    """The crumb takes a whole row on a wrapped bar, which is right between 480 and
    560 - the controls need two rows there regardless, so the crumb's own row is free -
    and wrong below 460, where it is a third row nobody is paying for. 90px to 71px.

    Both sides are asserted, because the interesting property is not "the bar is
    shorter" but "the boundary is in the right place": a change that simply let the
    crumb share at every width would make 480-560 worse, 56px to 71px, and only the
    upper assertion here would notice."""
    _, port = served_collision
    with sync_playwright() as pw:
        for width in (360, 414, 460):
            browser, page = open_page(pw, port, PAGE, width=width, height=800)
            click_el(page, "#headline")
            measure = """() => ({
                bar: Math.round(
                    document.querySelector('.wt-bar').getBoundingClientRect().height),
                crumb: Math.round(
                    document.getElementById('wt-crumb').getBoundingClientRect().width)})"""
            # The saving, in the state the bar is ordinarily in: 90px to 71px.
            assert page.evaluate(measure)["bar"] <= 75, \
                f"the bar is {page.evaluate(measure)['bar']}px at {width}px"
            # The crumb has to stay legible in the bar's WORST state, where the long
            # status and the badge compete with it for the row - otherwise this trades
            # page area for an element name nobody can read, which is the crushed-to-4px
            # failure the .wt-crumb comment records.
            #
            # An assertion on the rendered OUTCOME, deliberately not on any one rule -
            # but `.wt-crumb { min-width: 110px }` in the 460px block is what actually
            # holds it, and `>= 110` is that floor's own value. Remove the floor and the
            # crumb measures 80px at 360, 72 at 414 and 95 at 460; the mutation dies here.
            #
            # This comment used to say the floor "was deleted once no test could make it
            # bite" and credit `.wt-status { flex: 1 1 0 }` instead. Both halves were
            # wrong and the CSS said so at the time. The mutation appeared to survive
            # three runs because THIS test was staging the failure incorrectly: it
            # injected `.wt-status { flex: 0 1 auto !important }` to "make the floor
            # bite", which does the opposite - it hands the crumb more room and hides
            # the floor entirely. A surviving mutation is evidence about the test before
            # it is evidence about the code, and a test that stages the condition it
            # checks for can stage it wrong.
            worst_case_bar(page)
            page.wait_for_timeout(120)
            crumb = page.evaluate(measure)["crumb"]
            assert crumb >= 110, f"the crumb is crushed to {crumb}px at {width}px"
            browser.close()
        # And the band where the whole-row crumb still earns its keep.
        for width in (480, 560):
            browser, page = open_page(pw, port, PAGE, width=width, height=800)
            click_el(page, "#headline")
            bar = page.evaluate(
                "Math.round(document.querySelector('.wt-bar').getBoundingClientRect().height)")
            assert bar <= 60, f"the bar regressed to {bar}px at {width}px"
            browser.close()


def test_the_dock_rides_above_the_sheet(served_collision):
    """They share the bottom-left corner, so the dock moves up by whatever the sheet is
    currently tall - which is what --wt-panel-h is measured for.

    The sheet has to be made SHORTER than its 45vh cap for this to test anything. With
    every group expanded the sheet is clamped at exactly 0.45 x the window, so
    `bottom: calc(45vh + 20px)` - a hardcoded constant that ignores the measurement
    entirely - passes just as well as reading the property. Collapsing the groups is
    what makes the measured height and the cap different numbers, and it is also the
    docstring's own claim ("the groups collapse") finally being exercised. The gap is
    then asserted exactly rather than as `<=`, because `dock.bottom <= panel.top` holds
    at equality and so survives deleting the 20px."""
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=360, height=740)
        # Nothing selected: no sheet, so the dock keeps its ordinary offset.
        assert page.evaluate(
            "getComputedStyle(document.getElementById('wt-root'))"
            ".getPropertyValue('--wt-panel-h').trim()") == "0px"
        click_el(page, "#headline")
        page.wait_for_function(
            "getComputedStyle(document.getElementById('wt-root'))"
            ".getPropertyValue('--wt-panel-h').trim() !== '0px'")
        page.evaluate(
            """() => document.querySelectorAll('.wt-panel .wt-legend')
                       .forEach(b => { if (b.getAttribute('aria-expanded') !== 'false') b.click(); })""")
        # Wait for the PROPERTY to catch up, not merely for the panel to shrink. The
        # collapse changes layout immediately; --wt-panel-h is written from a
        # ResizeObserver a frame later, and the dock's `bottom` calc resolves on the
        # recalc after that. Reading in between shows a dock still placed against the
        # previous height - which is what this waits out, and is itself the coupling
        # under test.
        page.wait_for_function(
            """() => { const h = document.querySelector('.wt-panel')
                         .getBoundingClientRect().height;
                       const v = getComputedStyle(document.getElementById('wt-root'))
                         .getPropertyValue('--wt-panel-h').trim();
                       return h < innerHeight * 0.45 - 4
                              && Math.abs(parseFloat(v) - h) <= 1; }""")
        boxes = page.evaluate(
            """() => { const g = s => { const r = document.querySelector(s).getBoundingClientRect();
                         return {t: Math.round(r.top), b: Math.round(r.bottom),
                                 h: Math.round(r.height)}; };
                       return {dock: g('.wt-dock'), panel: g('.wt-panel'),
                               cap: Math.round(innerHeight * 0.45)}; }""")
        assert boxes["panel"]["h"] < boxes["cap"], \
            f"the sheet is still at its cap, so the measurement is untested: {boxes}"
        # 20px, within a pixel of rounding on a fractional panel height. Tight enough
        # to still kill both mutations this exists for: dropping the `+ 20px` gives a
        # gap of 0, and hardcoding `calc(45vh + 20px)` instead of reading the measured
        # height gives about 80 once the groups are collapsed.
        gap = boxes["panel"]["t"] - boxes["dock"]["b"]
        assert abs(gap - 20) <= 1, \
            f"the dock rides {gap}px above the measured sheet, expected 20: {boxes}"
        browser.close()


def test_both_new_breakpoints_are_pinned_on_both_sides(served_collision):
    """A breakpoint tested only from one side is not pinned. With cases at 520 and 560
    but nothing between, moving the sheet's `max-width: 520px` to 559px changes no
    result; the same held for the bar's 460 against 480. Assert the width either side
    of each edge, so the number itself is what the test is about."""
    _, port = served_collision
    with sync_playwright() as pw:
        # The sheet's edge: at 520 the panel spans the window, at 521 it is a column.
        for width, is_sheet in ((520, True), (521, False)):
            browser, page = open_page(pw, port, PAGE, width=width, height=800)
            click_el(page, "#headline")
            got = page.eval_on_selector(
                ".wt-panel", "el => Math.round(el.getBoundingClientRect().width)")
            assert (got == width) == is_sheet, \
                f"panel is {got}px wide at {width}px; sheet expected: {is_sheet}"
            browser.close()

        # The bar's edge: at 460 the crumb shares a row, at 461 it takes its own.
        for width, shares in ((460, True), (461, False)):
            browser, page = open_page(pw, port, PAGE, width=width, height=800)
            click_el(page, "#headline")
            got = page.evaluate(
                """() => { const bar = document.querySelector('.wt-bar')
                             .getBoundingClientRect();
                           const crumb = document.getElementById('wt-crumb')
                             .getBoundingClientRect();
                           // Its own row means it spans the bar's content width; sharing
                           // means it is materially narrower than that.
                           return crumb.width < bar.width - 40; }""")
            assert got == shares, \
                f"crumb sharing={got} at {width}px, expected {shares}"
            browser.close()


def test_the_h_guards_that_are_documented_are_real(served_collision):
    """Three separate conditions guard the key, and each was only described, not
    covered: a page's own contenteditable (the docstring's headline case, which the
    fixture had no example of), the modifier exclusions, and the mid-gesture guard.
    Removing any of them left the suite green."""
    _, port = served_collision
    with sync_playwright() as pw:
        # (a) the PAGE's own editable region - not an <input>, so the tag check alone
        #     does not cover it.
        browser, page = open_page(pw, port, PAGE, width=1280, height=900)
        page.evaluate(
            """() => { const p = document.getElementById('intro');
                       p.contentEditable = 'true'; p.focus(); }""")
        page.keyboard.press("h")
        page.wait_for_timeout(150)
        assert not peeking(page), "H peeked out of a page's contenteditable"
        browser.close()

        # (b) modifiers. Ctrl+H is the browser's history and Shift+H is a capital H.
        for combo in ("Control+h", "Shift+h", "Alt+h"):
            browser, page = open_page(pw, port, PAGE, width=1280, height=900)
            page.keyboard.press(combo)
            page.wait_for_timeout(150)
            assert not peeking(page), f"{combo} started a peek"
            browser.close()

        # (c) mid-gesture. The pointer owns the element and the chrome peek would
        #     uncover is not what the user is looking at.
        browser, page = open_page(pw, port, PAGE, width=1280, height=900)
        click_el(page, "#headline")
        p = centre(page, "#headline")
        page.mouse.move(p["x"], p["y"])
        page.mouse.down()
        page.mouse.move(p["x"] + 20, p["y"] + 12, steps=4)
        page.keyboard.press("h")
        page.wait_for_timeout(150)
        mid = peeking(page)
        page.mouse.up()
        assert not mid, "H peeked in the middle of a drag"
        browser.close()


def test_a_gesture_during_a_peek_records_nothing(served_collision):
    """The mirror of (c) above, and the half that was missing: that case starts a
    gesture and then presses H, this one peeks and then starts a gesture.

    Peek hides the grips precisely because they take clicks - but the selected
    element's own body takes a DRAG, and nothing in the drag path ever consulted the
    peek flag. So a drag while peeking recorded a nudge with every piece of editing UI
    invisible: no outline moving under the pointer, no change list, no Undo button, and
    the edit still bound for the edits file. An edit the user cannot see being made is
    worse than a lost one, because Reset is the only way back and nothing suggests it.

    Hiding the grips while leaving the body draggable was never a coherent position.
    """
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=1280, height=900)
        click_el(page, "#headline")
        assert selected(page) == "h1#headline"
        peek(page)
        p = centre(page, "#headline")
        page.mouse.move(p["x"], p["y"])
        page.mouse.down()
        page.mouse.move(p["x"] + 40, p["y"] + 24, steps=8)
        page.mouse.up()
        page.wait_for_timeout(150)
        moved = page.eval_on_selector(
            "#headline", "el => getComputedStyle(el).transform") != "none"
        undo_disabled = page.get_attribute("#wt-undo", "disabled") is not None
        browser.close()
    assert not moved, "a drag while peeking nudged the element with the chrome hidden"
    assert undo_disabled, "a drag while peeking recorded an undoable edit"


def test_the_peek_note_fits_the_narrowest_window(served_collision):
    """The note is the only thing on screen during a peek, and it is what names Esc.

    Everything else that teaches the key - the hint, the status line - is chrome, and
    peek's whole job is hiding the chrome. So this is the one piece of text that has to
    survive its own feature, and "discoverable at every width" rests on it. But it is
    `white-space: nowrap` and centred by `left: 50%` + `translateX(-50%)`, so it cannot
    reflow and cannot be pushed back inside: past its natural width it hangs off BOTH
    edges at once, losing the start and the end together. Every other note test runs at
    1280, where there is 900px of slack and nothing to find.

    320 rather than 360, and that is the point: the note measures 333.5px at EVERY
    width, so it clears 360 by 26.5px and hangs 6.8px off each edge at 320. Written at
    360 first, this test passed and proved nothing - the same "right assertion, wrong
    width" that the fixture rebuild in this changeset already had to undo once.
    """
    _, port = served_collision
    with sync_playwright() as pw:
        for width in (320, 360):
            browser, page = open_page(pw, port, PAGE, width=width, height=740)
            click_el(page, "#headline")
            peek(page)
            box = page.eval_on_selector(
                "#wt-peek-note",
                """el => { const r = el.getBoundingClientRect();
                           return { left: r.left, right: r.right }; }""")
            browser.close()
            assert box["left"] >= 0, \
                f"the peek note starts {-box['left']:.1f}px off the left edge at {width}px"
            assert box["right"] <= width, \
                f"the peek note runs {box['right'] - width:.1f}px past the right edge " \
                f"at {width}px"


def test_holding_h_down_does_not_strobe_the_chrome(served_collision):
    """Autorepeat is a keydown per repeat, and every one of them was a toggle.

    So resting a finger on H past the repeat delay flashed the whole Overlay on and off
    at the keyboard's repeat rate, and where it stopped depended on how many repeats
    the key had sent - an odd count and the chrome came back, an even one and it did
    not. Each toggle also ran closeAllSuggests() and a focus save/restore, so an open
    dropdown could not survive a leaning elbow either.

    Playwright cannot produce real autorepeat, so the repeats are dispatched as the
    browser sends them: keydown with `repeat: true`. The first press is a real one.
    """
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=1280, height=900)
        peek(page)
        page.evaluate(
            """() => { for (let i = 0; i < 5; i++)
                         document.dispatchEvent(new KeyboardEvent('keydown', {
                           key: 'h', bubbles: true, repeat: true })); }""")
        page.wait_for_timeout(150)
        assert peeking(page), "autorepeat toggled the peek back off underneath the user"
        browser.close()


def test_h_says_so_when_a_field_has_the_key(served_collision):
    """`h` is a letter, so a focused field keeps it - but peek has no button, so H is
    the only way in, and pressing it in a field used to do nothing and say nothing.
    The common way to end up here is clicking a page element that sits under the panel:
    the click lands on whichever control was painted there and takes focus."""
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=1280, height=900)
        click_el(page, "#headline")
        page.click("#wt-scope-input")
        page.keyboard.press("h")
        page.wait_for_function(
            "() => document.getElementById('wt-status').textContent.indexOf('H types') !== -1",
            timeout=2000)
        assert not peeking(page), "the guard let a peek through as well as reporting it"
        browser.close()


def test_the_guards_advice_actually_works(served_collision):
    """The guarded branch tells the user to "press Esc first to peek". A message that
    instructs someone to do something has to be a message the tool honours - and this
    one was not: Esc threw the selection away, left focus in the field, and the next H
    typed an `h` into it, leaving the Scope input reading "all widthsh". Asserting the
    string appeared was exactly the test that let that through, so this follows the
    advice literally and checks the outcome."""
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=1280, height=900)
        click_el(page, "#headline")
        page.click("#wt-scope-input")
        before = page.eval_on_selector("#wt-scope-input", "el => el.value")
        page.keyboard.press("h")
        page.wait_for_function(
            "() => document.getElementById('wt-status').textContent.indexOf('H types') !== -1")
        page.keyboard.press("Escape")                     # the advice, followed
        page.wait_for_function("() => !document.activeElement.closest('#wt-root')",
                               timeout=2000)
        assert selected(page) == "h1#headline", "Esc threw the selection away"
        peek(page)                                        # and now H works
        assert page.eval_on_selector("#wt-scope-input", "el => el.value") == before, \
            "an h was typed into the field on the way"
        browser.close()


def test_the_guards_advice_works_for_the_pages_own_fields_too(served_collision):
    """The twin of the test above, for the case the guard's own comment names first.

    `typingInto` deliberately covers the PAGE's fields, not only the Overlay's - its
    comment says exactly that - so H offers "press Esc first to peek" over a page's own
    input or contenteditable. But the Esc branch written to honour that advice was
    gated on `root.contains(activeElement)`, true only for the Overlay's own fields.
    One case narrower than the message it exists to serve. So on a page field the
    advice was still the destructive one it replaced: Esc fell through to deselect(),
    focus stayed put, and the next H typed an `h` into the user's page instead.

    Narrowing H to match Esc would be the wrong repair - `h` in a page field has to
    stay the letter h. It is the advice that has to become true.
    """
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=1280, height=900)
        click_el(page, "#headline")
        page.evaluate(
            """() => { const p = document.getElementById('intro');
                       p.contentEditable = 'true'; p.focus(); }""")
        before = page.eval_on_selector("#intro", "el => el.textContent")
        page.keyboard.press("h")
        page.wait_for_function(
            "() => document.getElementById('wt-status').textContent.indexOf('H types') !== -1")
        # The field keeps this one, and should: the guard returns WITHOUT
        # preventDefault because typing wins the key. "but not silently" is the status
        # line, not a swallowed keystroke - so the h lands in the page, as asked.
        typed = page.eval_on_selector("#intro", "el => el.textContent")
        assert typed != before, "the guard swallowed a letter the field had earned"
        page.keyboard.press("Escape")                     # the advice, followed
        page.wait_for_function(
            "() => document.activeElement !== document.getElementById('intro')",
            timeout=2000)
        assert selected(page) == "h1#headline", "Esc threw the selection away"
        peek(page)                                        # and now H works
        assert page.eval_on_selector("#intro", "el => el.textContent") == typed, \
            "the peek's own h was typed into the page as well"
        browser.close()


def test_peek_reaches_content_under_the_bottom_sheet(served_collision):
    """The both-halves pair for the newest region of chrome. The panel case above runs
    at 1280px, where the panel is a right-hand column - so until this, nothing ever
    click-selected through a hidden SHEET, which is the layout the whole footprint
    change introduced."""
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=360, height=800)
        click_el(page, "#headline")                       # opens the sheet
        assert page.eval_on_selector(
            ".wt-panel", "el => Math.round(el.getBoundingClientRect().width)") == 360, \
            "not the sheet layout, so this is testing the wrong thing"
        assert hit(page, "#widget") == "chrome", "the widget is not under the sheet"
        click_el(page, "#widget")
        assert selected(page) == "h1#headline", "widget selectable through the sheet"
        peek(page)
        click_el(page, "#widget")
        assert selected(page) == "div#widget", "peek did not reach under the sheet"
        browser.close()


def test_entering_a_peek_drops_the_stale_hover_box_too(served_collision):
    """Both edges of the toggle, which is what the code claims. Only the exit edge was
    covered: moving `hoverBox.hidden = true` inside the `if (!peeking)` branch - so it
    ran on the way out but not on the way in - left every peek test passing."""
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=1280, height=900)
        p = centre(page, "#intro")
        page.mouse.move(p["x"], p["y"])                   # draw a hover box on the page
        page.wait_for_function("!document.getElementById('wt-hover').hidden")
        page.keyboard.press("h")                          # keyboard: the pointer never moves
        page.wait_for_function(
            "document.getElementById('wt-root').classList.contains('wt-peek')")
        assert page.eval_on_selector("#wt-hover", "el => el.hidden"), \
            "a hover box survived into the peek"
        browser.close()


def test_peek_restores_the_keyboard_position(served_collision):
    """`visibility: hidden` makes the chrome non-focusable, so the browser drops focus
    to the body - right while peeking, useless afterwards. Without restoring it, every
    peek costs a keyboard user their place and the next Tab restarts at the top of the
    bar. A peek ended by a page CLICK deliberately does not restore: the point of that
    click is that the selection, not the old control, is the new subject."""
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=1280, height=900)
        page.click("#wt-deselect")
        assert page.evaluate("() => document.activeElement.id") == "wt-deselect"
        peek(page)
        page.wait_for_function("() => !document.activeElement.closest('#wt-root')",
                               timeout=2000)
        page.keyboard.press("h")
        page.wait_for_function(
            "!document.getElementById('wt-root').classList.contains('wt-peek')")
        assert page.evaluate("() => document.activeElement.id") == "wt-deselect", \
            "the keyboard position was not restored"

        # Ended by a click on the page instead: focus must NOT go back to the control.
        peek(page)
        click_el(page, "#nav")
        page.wait_for_function(
            "!document.getElementById('wt-root').classList.contains('wt-peek')")
        assert page.evaluate("() => document.activeElement.id") != "wt-deselect", \
            "focus was dragged back to a control the user had moved on from"
        browser.close()


def test_the_peek_note_names_the_key(served_collision):
    """It is the only thing on screen during a peek and its job is to say how to end
    one. Reducing its text to the bare word "Peeking" left every other assertion green
    - the note was tested for existence and for being un-clickable, never for saying
    anything. It carries role="status" so the change is announced, not merely drawn."""
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=1280, height=900)
        peek(page)
        note = page.eval_on_selector(
            "#wt-peek-note",
            "el => ({text: el.textContent, role: el.getAttribute('role')})")
        assert "H" in note["text"], f"the note does not name the key: {note['text']!r}"
        assert "Esc" in note["text"], f"the note omits Esc: {note['text']!r}"
        assert note["role"] == "status", "the note is not a live region"
        browser.close()


def test_the_dock_is_capped_against_the_panel_between_521_and_613(served_collision):
    """The rule this release repaired. It shipped inert in 0.7.1 - written above the
    `.wt-dock { width: 320px }` it was meant to override, so it lost the cascade - and
    deleting it outright still left the whole suite green, because nothing measured the
    dock in that band. Moving it back up, which is the exact original bug, has to fail
    something.

    Both edges of the band are pinned as well as its middle, because testing only the
    inside proved less than it looked: widening `max-width: 613` to 700, or dropping
    `min-width: 521` altogether, failed nothing at all. The band is not arbitrary. An
    uncapped dock spans 12..332 and the panel's left edge is `w - 282`, so the two stop
    overlapping at exactly 614 - which is why the cap ends at 613 and why the dock is
    back to its full 320px at 614, touching the panel without crossing it.
    """
    _, port = served_collision
    FULL = 320                                     # .wt-dock { width: 320px }, uncapped
    with sync_playwright() as pw:
        for width in (521, 560, 613):
            browser, page = open_page(pw, port, PAGE, width=width, height=800)
            click_el(page, "#headline")            # the panel is a column at these widths
            boxes = page.evaluate(
                """() => { const g = s => { const r = document.querySelector(s)
                             .getBoundingClientRect();
                             return {l: Math.round(r.left), r: Math.round(r.right),
                                     w: Math.round(r.width)}; };
                           return {dock: g('.wt-dock'), panel: g('.wt-panel')}; }""")
            assert boxes["dock"]["r"] <= boxes["panel"]["l"], \
                f"the dock reaches into the panel at {width}px: {boxes}"
            assert boxes["dock"]["w"] < FULL, \
                f"the cap is not applying at {width}px, inside the band: {boxes}"
            browser.close()

        # Both edges. 520 is the sheet layout, where the panel spans the window and the
        # dock is not capped against it; 614 is the first width where an uncapped dock
        # no longer reaches the panel. A cap applying at either would be the rule
        # escaping the band it was scoped to.
        for width in (520, 614):
            browser, page = open_page(pw, port, PAGE, width=width, height=800)
            click_el(page, "#headline")
            dock_w = page.evaluate(
                "Math.round(document.querySelector('.wt-dock').getBoundingClientRect().width)")
            assert dock_w == FULL, \
                f"the dock is capped at {width}px, outside the 521-613 band: {dock_w}px"
            browser.close()


def test_the_shape_palette_does_not_stretch_on_a_wrapped_bar(served_collision):
    """`.wt-palette` is anchored `right: 0`, and the wrapped-bar rule re-anchors it to
    `left: 12px` - so unless `right` is released the box is over-constrained the other
    way and stretches between both edges. Measured before the fix: 608px wide at a
    620px window, opaque and taking pointer events across all of it, and a click at the
    properties panel's top-right corner landed on the palette. That rule exists
    precisely to stop the palette eating panel clicks; it had moved the theft from one
    edge to the other."""
    _, port = served_collision
    with sync_playwright() as pw:
        for width in (1280, 700, 620, 480, 360):
            browser, page = open_page(pw, port, PAGE, width=width, height=800)
            click_el(page, "#headline")                    # opens the panel
            page.click("#wt-shape-btn")
            page.wait_for_selector("#wt-palette:not([hidden])")
            box = page.evaluate(
                """() => { const p = document.getElementById('wt-palette')
                             .getBoundingClientRect();
                           const panel = document.getElementById('wt-panel')
                             .getBoundingClientRect();
                           const h = document.elementFromPoint(
                               Math.round(panel.right - 8), Math.round(panel.top + 8));
                           return {w: Math.round(p.width),
                                   hit: h ? (h.id || h.className || h.tagName) : 'none'}; }""")
            assert box["w"] < 200, \
                f"the palette stretched to {box['w']}px at {width}px"
            assert "wt-palette" not in box["hit"], \
                f"the palette took the panel's click at {width}px (hit {box['hit']})"
            browser.close()


def test_the_band_picker_keeps_its_own_width(served_collision):
    """#wt-scope-list carries `wt-suggest-list wt-band-list`. The generic list is 236px
    and the band list wants 258px for a three-line row, but at equal specificity the
    generic rule - declared several hundred lines later - won, so band conditions
    ellipsised 22px earlier than intended at every width."""
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=1280, height=900)
        page.click("#wt-scope-toggle")
        page.wait_for_selector("#wt-scope-list:not([hidden])")
        width = page.eval_on_selector(
            "#wt-scope-list", "el => Math.round(el.getBoundingClientRect().width)")
        assert width == 258, f"the band list is {width}px, not its own 258px"
        browser.close()


def test_a_shape_placed_low_on_a_narrow_page_stays_visible(served_collision):
    """placeShape drops the shape where you clicked and selects it, which opens the
    sheet over the lower 45% - so a click down there produced a shape the user could
    not see, with no warning, because place mode hides the panel while they aim.

    One assertion covers two mistakes, and both were made: with no reveal at all the
    shape sits under the sheet, and with a reveal that clears only the sheet it lands
    under the dock riding above it. Asserting that nothing of the Overlay is on top of
    it is what catches either.

    Nine points, not the centre alone. Sampling only the middle asks a much weaker
    question than the docstring claims: a reveal that left half the shape under the
    sheet, or clipped its lower edge against the dock, passed a centre check without
    complaint. The corners are where a partial burial shows up.
    """
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=360, height=740)
        page.click("#wt-shape-btn")
        page.click('.wt-shape-item[data-shape="square"]')
        page.mouse.click(180, 600)                       # deep in the sheet's band
        page.wait_for_selector("svg.wt-shape")
        page.wait_for_timeout(250)                       # the reveal defers two frames
        state = page.evaluate(
            """() => { const s = document.querySelector('svg.wt-shape');
                       const b = s.getBoundingClientRect();
                       // Inset by 1px so a corner sample lands ON the shape rather
                       // than on whatever owns the boundary pixel.
                       const xs = [b.left + 1, b.left + b.width / 2, b.right - 1];
                       const ys = [b.top + 1, b.top + b.height / 2, b.bottom - 1];
                       const buried = [];
                       for (const x of xs) for (const y of ys) {
                         const e = document.elementFromPoint(Math.round(x), Math.round(y));
                         // A .wt-grip hit is not a burial: the grips are THIS shape's
                         // own resize handles and straddle its right and bottom edges
                         // on purpose, so three of the nine samples land on them by
                         // design. Counting them would make the test unsatisfiable for
                         // any selected element, which is every element it can run on.
                         if (e && e.closest('#wt-root') && !e.closest('.wt-grip'))
                           buried.push((e.id || e.className || e.tagName) +
                                       ' @' + Math.round(x) + ',' + Math.round(y));
                       }
                       const barH = document.querySelector('.wt-bar')
                                      .getBoundingClientRect().bottom;
                       return {buried: buried,
                               top: Math.round(b.top), bottom: Math.round(b.bottom),
                               barBottom: Math.round(barH),
                               viewH: window.innerHeight}; }""")
        assert not state["buried"], \
            f"the placed shape is buried at {len(state['buried'])} of 9 points: " \
            f"{state['buried']}"
        # Bounded on both sides. `top > 0` alone passes for a shape sitting at y=1 with
        # its whole body under the bar, which is the failure next door to this one.
        assert state["top"] >= state["barBottom"], \
            f"the shape's top ({state['top']}) is under the bar ({state['barBottom']})"
        assert state["bottom"] <= state["viewH"], \
            f"the shape runs past the bottom of the window ({state['bottom']} > " \
            f"{state['viewH']})"
        browser.close()


def test_the_reveal_leaves_an_already_visible_element_alone(served_collision):
    """In the sheet layout the reveal is armed, so the question is whether it knows to
    do nothing. It only works because chromeFloor excludes the BAR - the bar's top is
    0, so counting it makes the floor 0, every element "hidden", and every selection
    scroll. #headline sits at y=140 and this runs at 800 tall, so a 45vh sheet starts at
    440, comfortably clear, and the honest answer here is zero movement. (Said 407 at
    first, which is the figure for a 740-tall window - the height the other tests use.)"""
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=360, height=800)
        before = page.evaluate("window.scrollY")
        click_el(page, "#headline")
        page.wait_for_selector("#wt-panel:not([hidden])")
        page.wait_for_timeout(300)                   # past the reveal's two frames
        assert page.evaluate("window.scrollY") == before, \
            "the reveal scrolled an element that was already clear of the chrome"
        browser.close()


def test_the_reveal_leaves_the_column_layout_alone(served_collision):
    """Scrolling the page under someone is only worth it when the chrome genuinely
    covers what they selected. In the column layout the panel takes the right edge and
    never covers a full row, so nothing should move - the sheet is identified by
    spanning the window rather than by re-testing the breakpoint."""
    _, port = served_collision
    with sync_playwright() as pw:
        for width in (1280, 700):
            browser, page = open_page(pw, port, PAGE, width=width, height=800)
            before = page.evaluate("window.scrollY")
            click_el(page, "#intro")
            page.wait_for_timeout(250)
            assert page.evaluate("window.scrollY") == before, \
                f"the page scrolled on selection at {width}px"
            browser.close()


# --- the lifecycle ---------------------------------------------------------------

def test_selecting_during_a_peek_ends_it(served_collision):
    """Reaching a covered element is the reason to peek, so the click that reaches one
    finishes the job: the chrome returns with the panel already open on it."""
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=1280, height=900)
        peek(page)
        click_el(page, "#nav")
        page.wait_for_function(
            "!document.getElementById('wt-root').classList.contains('wt-peek')")
        assert not peeking(page)
        assert page.eval_on_selector("#wt-panel", "el => !el.hidden")
        browser.close()


def test_h_toggles_back(served_collision):
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=1280, height=900)
        peek(page)
        page.keyboard.press("h")
        page.wait_for_function(
            "!document.getElementById('wt-root').classList.contains('wt-peek')")
        assert hit(page, "#nav") == "chrome", "chrome did not come back"
        # The note is the one piece of chrome NOT hidden by the .wt-peek rule - it is
        # not .wt-ui, precisely so it survives to say why everything else went - which
        # means nothing else takes it away either. It has to hide itself.
        assert page.eval_on_selector("#wt-peek-note", "el => el.hidden"), \
            "the peek note stayed up after the peek ended"
        browser.close()


def test_escape_ends_the_peek_before_the_selection(served_collision):
    """Esc walks out of the newest layer, not the oldest - the same precedence the
    place-mode, suggestion-list and palette branches already follow."""
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=1280, height=900)
        click_el(page, "#headline")
        assert selected(page) == "h1#headline"
        peek(page)
        page.keyboard.press("Escape")
        page.wait_for_function(
            "!document.getElementById('wt-root').classList.contains('wt-peek')")
        assert selected(page) == "h1#headline", "Esc deselected as well as un-peeking"
        # And a second Esc still reaches the selection.
        page.keyboard.press("Escape")
        page.wait_for_function("document.getElementById('wt-selected').hidden")
        browser.close()


def test_h_is_ignored_while_typing_into_a_field(served_collision):
    """The panel is full of text inputs and "h" is a letter. Peeking mid-word would
    also blur the field it was typed into, losing the rest of the value."""
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=1280, height=900)
        click_el(page, "#headline")
        page.click("#wt-scope-input")
        before = page.eval_on_selector("#wt-scope-input", "el => el.value")
        page.keyboard.type("h")
        assert not peeking(page), "typing h into a field started a peek"
        # Asserted by length rather than by suffix: clicking a field puts the caret
        # where the pointer landed, not at the end, so the character arrives mid-word.
        after = page.eval_on_selector("#wt-scope-input", "el => el.value")
        assert len(after) == len(before) + 1 and after != before, \
            "the keystroke never reached the field"
        browser.close()


def test_peek_survives_the_bar_measurement(served_collision):
    """--wt-bar-h is measured from the rendered bar, and the panel, the dock and the
    place-hint all position against it. Hiding the chrome with `display: none` would
    measure 0 and misplace all three once the peek ended - so the height has to be
    unchanged during a peek, not merely restored after one."""
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=360, height=800)
        read = lambda: page.evaluate(                                  # noqa: E731
            "getComputedStyle(document.getElementById('wt-root'))"
            ".getPropertyValue('--wt-bar-h').trim()")
        before = read()
        assert before != "0px"
        peek(page)
        assert read() == before, "the bar was un-laid-out by the peek"
        page.keyboard.press("h")
        page.wait_for_function(
            "!document.getElementById('wt-root').classList.contains('wt-peek')")
        assert read() == before
        browser.close()


def test_the_peek_note_cannot_take_a_click(served_collision):
    """It is the one thing still painted over the page while peeking, so it is the one
    thing that could re-create the defect in miniature."""
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=1280, height=900)
        peek(page)
        assert page.eval_on_selector("#wt-peek-note", "el => !el.hidden")
        assert page.eval_on_selector(
            "#wt-peek-note", "el => getComputedStyle(el).pointerEvents") == "none"
        assert hit(page, "#wt-peek-note") == "page", "the note is hit-testable"
        browser.close()


def test_the_resize_grips_stop_taking_clicks(served_collision):
    """The grips are not .wt-ui - they live inside the selection box, which is
    pointer-events:none with the grips opting back in - so the rule that hides the
    chrome does not reach them. Three 11px squares latched to the selected element's
    right and bottom edges would keep swallowing clicks aimed at the page beneath."""
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=1280, height=900)
        click_el(page, "#headline")
        assert hit(page, ".wt-grip-br") == "chrome", "grip was not hit-testable to start"
        peek(page)
        assert page.eval_on_selector(
            ".wt-grip-br", "el => getComputedStyle(el).visibility") == "hidden"
        assert hit(page, ".wt-grip-br") == "page", "a grip still takes clicks while peeking"
        # The outlines themselves stay - they are pointer-events:none, so they cannot
        # intercept anything, and while peeking they are the only feedback about what
        # a click is about to select.
        assert page.eval_on_selector(
            "#wt-selected", "el => getComputedStyle(el).visibility") == "visible"
        browser.close()


def test_peek_moves_focus_out_of_the_hidden_chrome(served_collision):
    """`visibility: hidden` drops the chrome out of the tab order but cannot move a
    focus already inside it. A still-focused invisible button would take the Enter or
    Space meant for the page - and swallow the H that ends the peek."""
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=1280, height=900)
        page.click("#wt-deselect")                  # a bar control keeps focus
        assert page.evaluate(
            "() => !!document.activeElement.closest('#wt-root')"), \
            "the control did not take focus, so this proves nothing"
        peek(page)
        # Waited for, not asserted outright: the fixup is the browser's, and it runs on
        # the next style recalc rather than in the same task as the class change. An
        # immediate read passes or fails on timing - which it did, surviving three
        # unrelated mutations in one run and dying under them in another.
        page.wait_for_function(
            "() => !document.activeElement.closest('#wt-root')",
            timeout=2000)
        browser.close()


def test_ending_a_peek_drops_the_stale_hover_box(served_collision):
    """.wt-box outranks .wt-bar inside #wt-root's stacking context, so a hover box
    drawn on the nav - which only happens while peeking, because that is the only time
    the nav is the pointer's target - would paint ON TOP of the bar once the chrome
    came back, and stay there until the pointer next moved."""
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=1280, height=900)
        peek(page)
        p = centre(page, "#nav")
        page.mouse.move(p["x"], p["y"])         # hover the nav through the hidden bar
        page.wait_for_function("!document.getElementById('wt-hover').hidden")
        page.keyboard.press("h")                # toggle back without moving the pointer
        page.wait_for_function(
            "!document.getElementById('wt-root').classList.contains('wt-peek')")
        assert page.eval_on_selector("#wt-hover", "el => el.hidden"), \
            "a hover box was left painted over the bar"
        browser.close()


def test_peek_closes_the_shape_palette(served_collision):
    """An open dropdown is anchored to a control that is about to disappear, so
    leaving it up would paint a menu hanging off nothing."""
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=1280, height=900)
        page.click("#wt-shape-btn")
        assert page.eval_on_selector("#wt-palette", "el => !el.hidden")
        peek(page)
        assert page.eval_on_selector("#wt-palette", "el => el.hidden")
        browser.close()


def test_peek_closes_an_open_suggestion_list(served_collision):
    """The palette and the suggestion lists have separate lifecycles - the palette is
    not a .wt-suggest - so closing one is not closing the other. This is the second
    half, and it goes through closeAllSuggests rather than hiding the list directly
    because the toggle's aria-expanded has to come back down with it."""
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=1280, height=900)
        page.click("#wt-scope-toggle")
        assert page.eval_on_selector("#wt-scope-list", "el => !el.hidden")
        peek(page)
        assert page.eval_on_selector("#wt-scope-list", "el => el.hidden"), \
            "a suggestion list was left open behind the hidden chrome"
        assert page.eval_on_selector(
            "#wt-scope-toggle", "el => el.getAttribute('aria-expanded')") == "false"
        browser.close()


def test_h_does_nothing_while_placing_a_shape(served_collision):
    """In place mode the next click means "drop it here", not "select this", so a peek
    would hand the user a page they cannot actually click on."""
    _, port = served_collision
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, PAGE, width=1280, height=900)
        page.click("#wt-shape-btn")
        page.click('.wt-shape-item[data-shape="square"]')
        page.wait_for_selector("#wt-place-hint:not([hidden])")
        page.keyboard.press("h")
        assert not peeking(page), "peeked out of place mode"
        browser.close()
