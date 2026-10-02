"""Browser tests that the Overlay's band bookkeeping does not repeat work (issue 54).

Every record outside a gesture rebuilds the injected band stylesheet and, with the
changes list open, a summary per edited row. Both asked the browser for a fresh
MediaQueryList per band and re-parsed every condition, and both rewrote the sheet's
text even when it was identical. None of that changes any result, so these tests pin
that it is no longer done - by counting the work, not by timing it.
"""

from conftest import SAMPLE, open_page, pick, set_field

from _browser import sync_playwright, pytestmark  # noqa: F401

NARROW = "(max-width: 600px)"
FIVE = ["#headline", "p.eyebrow", "p.lede", "h2.section-title", "#ruled"]


def band_edit(page, selector, value):
    # Dispatched rather than clicked: at 480px the panel sheet covers most of the page.
    page.evaluate("s => document.querySelector(s).click()", selector)
    set_field(page, "#wt-fs", value)


def test_records_do_not_rebuild_media_query_lists_per_band(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        pick(page, NARROW)
        for i, sel in enumerate(FIVE):
            band_edit(page, sel, f"{20 + i}px")
        page.click("#wt-changes-head")     # the list is open, so every record summarises it
        assert page.evaluate(
            "() => document.querySelectorAll('#wt-changes-list .wt-change').length") >= 5
        page.evaluate(
            """() => {
                window.__mm = 0;
                const orig = window.matchMedia.bind(window);
                window.matchMedia = q => { window.__mm++; return orig(q); };
            }"""
        )
        for i in range(20):
            set_field(page, "#wt-fs", f"{30 + i}px")
        count = page.evaluate("() => window.__mm")
        # Guard: the 20 records really did record, so a zero count is not vacuous.
        assert page.evaluate(
            "() => document.getElementById('wt-fs').value") == "49px"
        assert page.evaluate(
            "() => document.getElementById('wt-band-style').textContent"
        ).count("font-size") == 5
        browser.close()
    assert count == 0, f"matchMedia was called {count} times across 20 records"


def test_a_base_edit_does_not_rewrite_an_unchanged_band_stylesheet(served):
    tmp, port = served
    with sync_playwright() as p:
        browser, page = open_page(p, port, width=480)
        pick(page, NARROW)
        band_edit(page, "#headline", "30px")
        # A base-only edit on an unrelated element: the band map is untouched.
        pick(page, "")      # the peel on this scope change is legitimate; observe after it
        page.evaluate(
            """() => {
                const el = document.getElementById('wt-band-style');
                // The callback tallies what it is handed: records are delivered at the
                // next microtask checkpoint, so takeRecords() alone would read zero
                // whether or not the sheet was rewritten.
                window.__muts = 0;
                window.__obs = new MutationObserver(r => { window.__muts += r.length; });
                window.__obs.observe(el, {childList: true, characterData: true,
                                          subtree: true});
            }"""
        )
        page.click("p.lede", position={"x": 8, "y": 8})
        set_field(page, "#wt-fs", "21px")
        quiet = page.evaluate("() => window.__muts + window.__obs.takeRecords().length")

        # The same observer must still see a banded edit, or the zero above is vacuous.
        pick(page, NARROW)
        band_edit(page, "p.eyebrow", "29px")
        seen = page.evaluate("() => window.__muts + window.__obs.takeRecords().length")
        browser.close()
    assert quiet == 0, f"the band stylesheet was rewritten {quiet} times for a base edit"
    assert seen > 0, "the observer saw no mutation for a banded edit; the guard is vacuous"
