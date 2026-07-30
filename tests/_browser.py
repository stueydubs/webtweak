"""The Playwright gate, in one place.

Every browser module needs the same three things: skip loudly when Playwright is
absent, import `sync_playwright`, and carry the `browser` marker so CI selects it
by property rather than by filename. Repeating that per file is exactly how a
module ends up unmarked - rejoining the unit job, hitting the skip, and reading
green while never executing. Importing this module supplies all three.

    from _browser import sync_playwright, pytestmark   # noqa: F401
"""

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="install Playwright to run the browser e2e - see the README's Development "
           "section: pip install -r requirements-dev.txt && playwright install chromium",
)

from playwright.sync_api import sync_playwright  # noqa: E402,F401

pytestmark = pytest.mark.browser
