"""Watcher behaviour, driven through the real SSE endpoint.

The watcher is what makes the loop visible, and its failure mode is silent: it
just stops firing and the user quietly goes back to reloading by hand. These
tests pin the cases that produced exactly that.
"""

import shutil
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from _server import start, stop


class Stream:
    """Reads the SSE endpoint on a thread; `wait_for` polls what has arrived."""

    def __init__(self, port):
        self.lines = []
        self._stop = False
        self._t = threading.Thread(target=self._run, args=(port,), daemon=True)
        self._t.start()
        self.wait_for("retry:", timeout=5)          # connected

    def _run(self, port):
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/__webtweak__/events", timeout=30) as r:
                for raw in r:
                    if self._stop:
                        return
                    self.lines.append(raw.decode("utf-8", "replace"))
        except Exception:
            pass

    @property
    def text(self):
        return "".join(self.lines)

    def wait_for(self, needle, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if needle in self.text:
                return True
            time.sleep(0.02)
        return False

    def clear(self):
        self.lines = []

    def close(self):
        self._stop = True


@pytest.fixture
def site():
    tmp = Path(tempfile.mkdtemp())
    (tmp / "css").mkdir()
    (tmp / "css" / "main.css").write_text("h1{color:crimson}\n")
    page = tmp / "page.html"
    page.write_text("<html><body><h1>Hi</h1></body></html>\n")
    proc, port = start(page)
    stream = Stream(port)
    yield tmp, port, stream
    stream.close()
    stop(proc)
    shutil.rmtree(tmp, ignore_errors=True)


def test_source_change_fires(site):
    tmp, _, stream = site
    (tmp / "css" / "main.css").write_text("h1{color:navy}\n")
    assert stream.wait_for("source-change")
    assert "main.css" in stream.text


def test_recreated_directory_is_rewatched(site):
    """A stale watcher entry for a deleted directory used to make watchers.has()
    true forever, so a recreated directory of the same name was never watched
    again and live reload silently died for that whole subtree."""
    tmp, _, stream = site
    shutil.rmtree(tmp / "css")
    stream.wait_for("source-change")                # the removal itself
    (tmp / "css").mkdir()
    time.sleep(0.4)                                 # let the new dir get watched
    stream.clear()
    (tmp / "css" / "site.css").write_text("h1{color:green}\n")
    assert stream.wait_for("source-change"), "recreated directory is not watched"


def test_a_directory_created_after_boot_is_watched(site):
    tmp, _, stream = site
    (tmp / "later").mkdir()
    time.sleep(0.4)
    stream.clear()
    (tmp / "later" / "x.css").write_text("p{color:red}\n")
    assert stream.wait_for("source-change")


def test_user_files_named_tmp_or_bak_are_not_ignored(site):
    """The exclusion exists to stop webtweak's OWN artefacts bouncing the page.
    Matching bare .tmp/.bak also hid the user's files of those names."""
    tmp, _, stream = site
    (tmp / "notes.tmp").write_text("x\n")
    assert stream.wait_for("source-change"), "a user's .tmp file should still count as source"
    stream.clear()
    (tmp / "report.bak").write_text("y\n")
    assert stream.wait_for("source-change"), "a user's .bak file should still count as source"


def test_webtweak_artefacts_never_fire_a_source_change(site):
    """Saving must not bounce the page the user is still editing."""
    tmp, _, stream = site
    (tmp / "page.webtweak.json.1234.tmp").write_text("{}\n")
    (tmp / "page.webtweak.json.2026-01-01.bak").write_text("{}\n")
    time.sleep(0.6)
    assert "source-change" not in stream.text


def test_edits_file_is_reported_separately(site):
    """`mark` touches only the edits file. It must reach the page as its own
    event, or the badge can never reach 'reconciled'."""
    tmp, _, stream = site
    (tmp / "page.webtweak.json").write_text('{"batches": []}\n')
    assert stream.wait_for("edits-change")
    assert "source-change" not in stream.text


def test_symlink_out_of_the_served_root_is_not_watched(site):
    """The initial walk refuses to follow symlinks, but an fs.watch event only
    carries a name, so the child gets stat'd - and a stat follows links. Without
    a containment check a link created at runtime had us watching outside."""
    tmp, _, stream = site
    outside = Path(tempfile.mkdtemp())
    try:
        (outside / "secret").mkdir()
        (tmp / "shared").symlink_to(outside)
        stream.wait_for("source-change")            # creating the link itself
        time.sleep(0.4)
        stream.clear()
        (outside / "secret" / "leak.txt").write_text("private\n")
        time.sleep(0.8)
        assert "source-change" not in stream.text, "watching outside the served root"
    finally:
        shutil.rmtree(outside, ignore_errors=True)
