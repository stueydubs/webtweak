"""Browser test that restore() walks the page's stylesheets once, not once per banded
group (issue 54).

rememberBand used to call pageConditions() per banded group, so a long pending batch
cost patches x rules on every load. The count here is of reads of `cssRules`, which is
what the walk is made of, and the bound does not mention the patch count.
"""

from conftest import SAMPLE, seed_batch

from _browser import sync_playwright, pytestmark  # noqa: F401

PATCHES = 30

COUNT_CSSRULES = """(() => {
    window.__cssRulesReads = 0;
    for (const C of [CSSStyleSheet, CSSGroupingRule]) {
        const d = Object.getOwnPropertyDescriptor(C.prototype, 'cssRules');
        Object.defineProperty(C.prototype, 'cssRules', {
            configurable: true, enumerable: d.enumerable,
            get() { window.__cssRulesReads++; return d.get.call(this); },
        });
    }
})();"""


def test_restoring_a_long_banded_batch_does_not_rewalk_the_stylesheets_per_patch(served):
    tmp, port = served
    edits_file = tmp / "sample.webtweak.json"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        ctx.add_init_script(COUNT_CSSRULES)
        page = ctx.new_page()
        page.goto(f"http://127.0.0.1:{port}/{SAMPLE}")
        page.wait_for_selector("#wt-root")
        session = page.evaluate("() => sessionStorage.getItem('wt-session-sample.html')")
        targets = page.evaluate(
            """() => [...document.querySelectorAll('body *')]
                .filter(e => !e.closest('#wt-root') && !e.closest('svg')
                             && !['SCRIPT', 'STYLE', 'LINK'].includes(e.tagName)
                             && !e.id.startsWith('wt-') && e.id !== 'wt-band-style')
                .map(e => {
                    const path = [];
                    for (let n = e; n && n !== document.body; n = n.parentElement)
                        path.unshift(n.tagName.toLowerCase() + ':nth-child('
                                     + (Array.prototype.indexOf.call(n.parentElement.children, n) + 1) + ')');
                    return {tag: e.tagName.toLowerCase(), sel: 'body > ' + path.join(' > ')};
                })"""
        )
        assert len(targets) >= 5
        patch_list = [{
            "fingerprint": {"tag": t["tag"], "id": "", "classes": [], "text": "",
                            "ownText": "", "selector": t["sel"], "siblingIndex": 0,
                            "openTag": "<" + t["tag"] + ">"},
            "changes": {},
            "media": {f"(max-width: {300 + n}px)": {"letter-spacing": "1px"}},
        } for n, t in ((n, targets[n % len(targets)]) for n in range(PATCHES))]
        seed_batch(edits_file, session, patch_list)
        page.reload()
        page.wait_for_selector("#wt-root")
        page.wait_for_function(
            "document.getElementById('wt-status').textContent.indexOf('restored') !== -1")
        restored = page.evaluate("() => document.getElementById('wt-status').textContent")
        reads = page.evaluate("() => window.__cssRulesReads")
        bound = page.evaluate(
            """() => {
                let nested = 0;
                const walk = rules => Array.prototype.forEach.call(rules, r => {
                    if (r instanceof CSSGroupingRule) { nested++; walk(r.cssRules); }
                });
                for (const s of document.styleSheets) {
                    try { walk(s.cssRules); } catch (e) {}
                }
                return 3 * (document.styleSheets.length + nested);
            }"""
        )
        browser.close()
    assert f"restored {PATCHES}" in restored, f"patches did not restore: {restored}"
    assert reads <= bound, (
        f"{reads} cssRules reads while restoring {PATCHES} banded patches; "
        f"a once-per-restore walk needs at most {bound}")
