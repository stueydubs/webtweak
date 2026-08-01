"""Tests for `--root`: serving a web root above the page.

Without it, webtweak serves the page's own folder, so a page in a subfolder that
references root-absolute assets (`/css/site.css`) renders unstyled - which is
most real sites. The edits file must still land beside the *page*, not in the
web root, or the loop writes its hand-off artefact somewhere Claude won't look.
"""

import json
import shutil
import subprocess
import urllib.error
import urllib.request

import pytest

from _server import ROOT, start, stop


def get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}") as r:
        return r.status, r.read().decode("utf-8")


def status(port, path):
    try:
        return get(port, path)[0]
    except urllib.error.HTTPError as e:
        return e.code


@pytest.fixture
def site(tmp_path):
    """A page in a subfolder referencing a root-absolute stylesheet."""
    (tmp_path / "css").mkdir()
    (tmp_path / "blog").mkdir()
    (tmp_path / "css" / "main.css").write_text("h1{color:crimson}\n")
    (tmp_path / "blog" / "post.html").write_text(
        '<html><head><link rel="stylesheet" href="/css/main.css"></head>'
        "<body><h1>Post</h1></body></html>\n"
    )
    return tmp_path


def test_without_root_a_root_absolute_asset_404s(site):
    """The limitation --root exists to remove. Documents current behaviour so a
    future change to the default is a deliberate decision, not a surprise."""
    proc, port = start(site / "blog" / "post.html")
    try:
        assert status(port, "/css/main.css") == 404
    finally:
        stop(proc)


def test_root_serves_the_asset_and_the_page(site):
    proc, port = start(site / "blog" / "post.html", root=site)
    try:
        assert status(port, "/css/main.css") == 200
        code, body = get(port, "/blog/post.html")
        assert code == 200
        assert "__WEBTWEAK__" in body      # the page still gets the overlay
    finally:
        stop(proc)


def test_root_still_contains_traversal(site):
    """A wider root must not mean a weaker containment guard.

    Note what this does and does not prove. The OUTCOME is defended twice - by
    `contained(local, serveRoot)` and again by the realpath check - so deleting either
    one alone leaves this green. That is defence in depth working, not a gap; the test
    is deliberately on the outcome, because the outcome is the thing that must hold.
    Asserting the body as well as the status is what makes it about the file rather
    than about which branch produced the refusal.
    """
    proc, port = start(site / "blog" / "post.html", root=site)
    try:
        for path in ("/../../etc/passwd", "/..%2f..%2fetc%2fpasswd", "/blog/../../etc/passwd"):
            try:
                code, body = get(port, path)
            except urllib.error.HTTPError as e:
                code, body = e.code, e.read().decode("utf-8", "replace")
            assert code in (400, 403, 404), (path, code)
            assert "root:x:" not in body, path
    finally:
        stop(proc)


def test_edits_file_lands_beside_the_page_not_the_root(site):
    """The edits file is the hand-off artefact and CONTEXT.md places it next to
    the Target page. With --root those are different directories."""
    page = site / "blog" / "post.html"
    proc, port = start(page, root=site)
    try:
        payload = json.dumps({
            "target": "post.html", "sessionId": "s1", "viewport": 1280,
            "patches": [{"fingerprint": {"tag": "h1"}, "changes": {"color": "#111"}}],
        }).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/__webtweak__/save", data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as r:
            assert r.status == 200
    finally:
        stop(proc)

    assert (site / "blog" / "post.webtweak.json").is_file()
    assert not (site / "post.webtweak.json").exists()


def test_edits_endpoint_reads_the_same_file(site):
    page = site / "blog" / "post.html"
    (site / "blog" / "post.webtweak.json").write_text(
        json.dumps({"target": "post.html", "batches": [
            {"sessionId": "s1", "status": "pending", "patches": []}]}))
    proc, port = start(page, root=site)
    try:
        code, body = get(port, "/__webtweak__/edits")
        assert code == 200
        assert json.loads(body)["batches"][0]["sessionId"] == "s1"
    finally:
        stop(proc)


@pytest.mark.parametrize("args,expected", [
    (["--root", "/nonexistent-webtweak-root"], "no such directory"),
    (["--root"],                               "needs a directory"),
])
def test_root_validation_messages(site, args, expected):
    page = str(site / "blog" / "post.html")
    r = subprocess.run(["node", str(ROOT / "webtweak.js"), page, *args],
                       capture_output=True, text=True, timeout=10)
    assert r.returncode != 0
    assert expected in r.stderr


def test_root_must_contain_the_page(site, tmp_path):
    elsewhere = tmp_path.parent / "elsewhere-root"
    elsewhere.mkdir(exist_ok=True)
    try:
        r = subprocess.run(
            ["node", str(ROOT / "webtweak.js"), str(site / "blog" / "post.html"),
             "--root", str(elsewhere)],
            capture_output=True, text=True, timeout=10)
        assert r.returncode != 0
        assert "must contain the page" in r.stderr
    finally:
        shutil.rmtree(elsewhere, ignore_errors=True)
