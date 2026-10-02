"""The watcher must see the edits file when the page is reached through a symlink.

The watcher builds each changed path from the directory it watches, and the edits
path comes from the REAL target path. If the watcher walks a raw (symlinked) root
the two never compare equal, classify() takes the edits file for webtweak's own
churn, and no edits-change event is ever broadcast.
"""

import shutil
import tempfile
import time
from pathlib import Path

import pytest

from _server import start, stop
from test_watcher import Stream


@pytest.fixture
def real_and_link():
    base = Path(tempfile.mkdtemp())
    real = base / "real"
    real.mkdir()
    (real / "p.html").write_text("<html><body><h1>Hi</h1></body></html>\n")
    link = base / "link"
    link.symlink_to(real)
    yield real, link
    shutil.rmtree(base, ignore_errors=True)


def _run(page, root, real):
    proc, port = start(page, root=root)
    stream = Stream(port)
    try:
        time.sleep(0.3)
        # Positive control: an ordinary file proves this server's watcher is alive.
        (real / "other.html").write_text("<p>x</p>\n")
        assert stream.wait_for("source-change"), "watcher is dead; the edits assertion would be vacuous"
        stream.clear()
        (real / "p.webtweak.json").write_text('{"batches": []}\n')
        assert stream.wait_for("edits-change"), "edits-change never fired"
        assert "source-change" not in stream.text
    finally:
        stream.close()
        stop(proc)


def test_edits_change_fires_when_the_page_is_addressed_through_a_symlinked_directory(real_and_link):
    real, link = real_and_link
    _run(link / "p.html", None, real)


def test_edits_change_fires_with_a_symlinked_root(real_and_link):
    real, link = real_and_link
    _run(real / "p.html", link, real)
