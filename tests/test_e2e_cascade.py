"""The cascade-order trap in overlay.css, and the three rules it broke.

Not peek tests, and they were in the peek module only because they were found while
doing peek. What they share is a cause: overlay.css declares most of its @media blocks
around line 200 but the components they override several hundred lines further down,
so a rule written up there loses at equal specificity to the base rule below it. It is
silent - the rule is valid, it just never wins - and one of these three shipped that
way in 0.7.1 and left the whole suite green.

Two of them turn on a second shape of the same trap: an element carrying TWO classes
whose rules conflict, where the loser is not the one written earlier but the one on the
class the reader did not have in mind. #wt-scope is `wt-scope wt-suggest`, and
#wt-scope-list is `wt-suggest-list wt-band-list`.

Each test asserts the RENDERED outcome rather than the rule, because the rule being
present is exactly what was true while it did nothing.
"""

from conftest import (COLLISION, click_el, open_page,  # noqa: F401
                      served_collision)

from _browser import sync_playwright, pytestmark  # noqa: F401

PAGE = COLLISION


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
            # 170 rather than 200. The palette's width is content-determined and
            # deterministic - three 40px items plus gaps, padding and borders, 150px at
            # every width it wraps at - so `< 200` carried 50px of slack for no reason.
            # It was 608px at a 620px window before the fix, so either bound kills that,
            # but the tighter one also catches a partial stretch.
            assert box["w"] < 170, \
                f"the palette stretched to {box['w']}px at {width}px (natural width 150)"
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
