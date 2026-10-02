"""The Overlay must boot on a page whose filename is not ASCII.

serveHtml re-encodes the document through latin1, so the injected target name has
to be pure ASCII or the page sees a different string from the URL and overlay.js
returns silently. See overlayMarkup in webtweak.js.
"""

import shutil
import tempfile
from pathlib import Path
from urllib.parse import quote

import pytest

from _server import ROOT, start, stop
from conftest import open_page

from _browser import sync_playwright, pytestmark  # noqa: F401


@pytest.fixture(params=["café.html", "日本語.html"])
def served_non_ascii(request):
    tmp = Path(tempfile.mkdtemp())
    page = tmp / request.param
    shutil.copy(ROOT / "fixtures" / "sample.html", page)
    proc, port = start(page)
    yield port, request.param
    stop(proc)
    shutil.rmtree(tmp, ignore_errors=True)


def test_overlay_mounts_on_a_page_with_a_non_ascii_filename(served_non_ascii):
    port, name = served_non_ascii
    with sync_playwright() as p:
        # open_page waits for #wt-root, so a silent refusal to boot times out here.
        browser, page = open_page(p, port, quote(name))
        assert page.evaluate("window.__WEBTWEAK__.target") == name
        assert page.locator("#wt-root").count() == 1
        browser.close()
