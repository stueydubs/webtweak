"""The Playwright gate, in one place.

Every browser module needs the same three things: skip loudly when Playwright is
absent, import `sync_playwright`, and carry the `browser` marker so CI selects it
by property rather than by filename. Repeating that per file is exactly how a
module ends up unmarked - rejoining the unit job, hitting the skip, and reading
green while never executing. Importing this module supplies all three.

    from _browser import sync_playwright, pytestmark   # noqa: F401
"""

import contextlib

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="install Playwright to run the browser e2e - see the README's Development "
           "section: pip install -r requirements-dev.txt && playwright install chromium",
)

from playwright.sync_api import sync_playwright as _real_sync_playwright  # noqa: E402

pytestmark = pytest.mark.browser

_shared = None


@contextlib.contextmanager
def _shared_playwright():
    global _shared
    if _shared is None:
        _shared = _real_sync_playwright().start()
    try:
        yield _shared
    finally:
        # The Playwright and its Chromium outlive the block, but whatever contexts the
        # test left open do not: a test that fails before its `browser.close()` used to
        # lose them when the block stopped Playwright, and must not leak them into the
        # next test now that nothing does.
        browser = getattr(_shared, "_wt_browser", None)
        if browser is not None and browser.is_connected():
            for ctx in list(browser.contexts):
                try:
                    ctx.close()
                except Exception:
                    pass


def sync_playwright(own=False):
    """Drop-in for Playwright's `sync_playwright()`, sharing one instance per session.

    Starting a driver and launching Chromium per test cost about 91ms each, most of a
    230 second run, and `open_page` cannot cache a browser on a Playwright object that
    dies with the test. So every `with sync_playwright() as p:` block yields the same
    session-wide Playwright, started on first use and stopped by `stop_shared_playwright`
    from conftest's `pytest_sessionfinish`. Exiting the block closes the contexts the
    block's browser still holds and nothing else. Contexts are what give a test its
    isolation; the browser process is the part that was being rebuilt for nothing.

    `own=True` hands back Playwright's own context manager, with its own driver and
    its own browser that stop when the block does, for a test that must be able to
    kill or reconfigure the browser without affecting its neighbours. Playwright's
    sync API refuses a second instance in the same thread, so the shared one is
    stopped first and restarted lazily by the next shared block. That makes the opt-out
    costly and means it cannot be entered inside a shared block, which is fine for the
    rare test that wants it.
    """
    if own:
        stop_shared_playwright()
        return _real_sync_playwright()
    return _shared_playwright()


def stop_shared_playwright():
    global _shared
    if _shared is not None:
        pw, _shared = _shared, None
        pw.stop()
