"""One Chromium for the whole browser suite, not one per test.

`_browser.sync_playwright` yields a session-wide Playwright, so `open_page`'s
`_wt_browser` cache outlives each test's `with` block. The first two tests each
open a page and record which browser served it; the third compares them. They are
ordered by definition within the module and share state through `SEEN` on purpose.

The browser objects are kept, not just their ids: `id()` can be reused once an
object is collected, so a per-test launch could otherwise compare equal by luck of
the allocator and pass for the wrong reason.
"""

from _browser import sync_playwright, pytestmark  # noqa: F401
from conftest import open_page

SEEN = []


def _record(port):
    with sync_playwright() as p:
        ctx, page = open_page(p, port)
        SEEN.append((id(p._wt_browser), p._wt_browser))
        ctx.close()


def test_first_open_records_its_browser(served):
    _record(served[1])


def test_second_open_records_its_browser(served):
    _record(served[1])


def test_both_opens_shared_one_connected_browser():
    assert len(SEEN) == 2, "the two recording tests must run first, in this module"
    (first_id, _), (second_id, browser) = SEEN
    assert first_id == second_id
    assert browser.is_connected()


def test_own_opts_out_to_a_separate_browser(served):
    with sync_playwright() as shared:
        open_page(shared, served[1])[0].close()
        shared_browser = shared._wt_browser
    with sync_playwright(own=True) as own:
        assert own is not shared
        ctx, _ = open_page(own, served[1])
        assert own._wt_browser is not shared_browser
        ctx.close()
    with sync_playwright() as again:     # the shared one comes back lazily
        ctx, _ = open_page(again, served[1])
        assert again._wt_browser.is_connected()
        ctx.close()
