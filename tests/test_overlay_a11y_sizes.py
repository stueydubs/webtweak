"""Muted overlay text reaches WCAG AA 4.5:1, and the small controls reach 24x24.

Contrast is computed from `getComputedStyle`, resolving each background by walking up
to the first opaque ancestor, rather than from hex values read out of the stylesheet:
a hex in a rule says nothing about what a rule further down the cascade did to it.
Size is `getBoundingClientRect`, because a min-width the cascade overrode is the same
as no min-width.
"""

import pytest

from conftest import open_page, set_field

from _browser import sync_playwright, pytestmark  # noqa: F401

MIN_CONTRAST = 4.5
MIN_TARGET = 24

# Evaluated in the page. Returns [colour, background, text] for a selector, the
# background being the first ancestor (or the element itself) with alpha > 0.
COLOURS = """sel => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const parse = c => (c.match(/[\\d.]+/g) || []).map(Number);
    const fg = parse(getComputedStyle(el).color);
    let bg = null;
    for (let n = el; n; n = n.parentElement) {
        const c = parse(getComputedStyle(n).backgroundColor);
        if (c.length === 3 || c[3] === 1) { bg = c; break; }
    }
    return {fg: fg, bg: bg, text: el.textContent.trim()};
}"""


def luminance(rgb):
    def lin(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(v) for v in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg, bg):
    hi, lo = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_the_contrast_helper_matches_known_ratios():
    """The helper is the instrument; check it against two published values first."""
    assert contrast((0, 0, 0), (255, 255, 255)) == pytest.approx(21.0)
    assert contrast((0x71, 0x77, 0x84), (0x1a, 0x1d, 0x23)) == pytest.approx(3.76, abs=0.02)


def test_muted_overlay_text_is_at_least_4_5_to_1(served):
    _, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")                        # the panel only fills on a selection
        page.click("#wt-scope-toggle")                 # open the band list
        page.wait_for_selector("#wt-scope-list .wt-band-note", state="visible")
        found = {}
        for name, sel in {
            "Applies at label": ".wt-scope-label",
            "group heading": ".wt-group > .wt-legend",
            "panel note": ".wt-note",
            "band note": "#wt-scope-list .wt-band-note",
        }.items():
            found[name] = page.evaluate(COLOURS, sel)
        browser.close()
    for name, c in found.items():
        assert c, f"{name}: no element matched, so nothing was measured"
        assert c["bg"], f"{name}: no opaque background found above it"
        assert c["text"], f"{name}: matched an empty element"
        ratio = contrast(c["fg"], c["bg"])
        assert ratio >= MIN_CONTRAST, \
            f"{name}: {c['fg']} on {c['bg']} is {ratio:.2f}:1, under {MIN_CONTRAST}:1"


def test_the_small_controls_have_a_24px_hit_box(served):
    _, port = served
    sizes = {}
    with sync_playwright() as p:
        browser, page = open_page(p, port)
        page.click("#headline")
        set_field(page, "#wt-lh", "1.3")               # an edit, so the revert dot shows
        page.wait_for_selector(".wt-revert:not([hidden])")
        for name, sel in {
            "stepper button": ".wt-step-btns button",
            "suggest toggle": ".wt-suggest-toggle",
            "link": ".wt-link",
            "revert": ".wt-revert:not([hidden])",
        }.items():
            sizes[name] = page.locator(sel).first.bounding_box()
        grips = page.locator("#wt-selected .wt-grip")
        assert grips.count() == 3, "the three resize grips were not all found"
        for i in range(grips.count()):
            sizes[f"grip {i}"] = grips.nth(i).bounding_box()
        browser.close()
    for name, box in sizes.items():
        assert box, f"{name}: not rendered, so nothing was measured"
        assert box["width"] >= MIN_TARGET and box["height"] >= MIN_TARGET, \
            f"{name}: {box['width']}x{box['height']}, under {MIN_TARGET}x{MIN_TARGET}"
