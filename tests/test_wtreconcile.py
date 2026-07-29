"""Tests for the reconcile helper (reconcile/scripts/wtreconcile.py).

The helper is the only executable half of reconcile - the rest is judgment work
in SKILL.md - so what it guarantees matters: it must never silently retire a
batch, and it must fail cleanly (not with a raw traceback) on a corrupt file.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "reconcile" / "scripts" / "wtreconcile.py"


def run(*args, cwd=None):
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, cwd=cwd)


def write(tmp_path, doc):
    f = tmp_path / "page.webtweak.json"
    f.write_text(json.dumps(doc), encoding="utf-8")
    return f


def batch(session="s1", status="pending", patches=None):
    return {
        "sessionId": session,
        "savedAt": "2026-07-29T10:00:00",
        "viewport": 1280,
        "status": status,
        "patches": patches if patches is not None else [
            {"fingerprint": {"tag": "h1", "id": "headline"},
             "changes": {"font-size": "52px"}}
        ],
    }


# --- pending ---------------------------------------------------------------

def test_pending_lists_a_pending_batch(tmp_path):
    f = write(tmp_path, {"target": "page.html", "batches": [batch()]})
    r = run("pending", str(f))
    assert r.returncode == 0
    assert "session=s1" in r.stdout
    assert "h1#headline" in r.stdout


def test_pending_ignores_reconciled_batches(tmp_path):
    f = write(tmp_path, {"target": "page.html", "batches": [batch(status="reconciled")]})
    r = run("pending", str(f))
    assert r.returncode == 0
    assert "no pending batches" in r.stdout


def test_pending_flags_a_create_patch(tmp_path):
    """A create patch needs a different reconcile path, so it must not read as an
    ordinary edit patch in the summary."""
    f = write(tmp_path, {"target": "page.html", "batches": [batch(patches=[
        {"op": "create", "shape": "triangle",
         "fingerprint": {"tag": "svg", "id": "wt-shape-a1b2c3"},
         "changes": {"fill": "#3366cc"}},
    ])]})
    r = run("pending", str(f))
    assert r.returncode == 0
    assert "create triangle" in r.stdout


# --- corrupt input ---------------------------------------------------------

@pytest.mark.parametrize("doc", [
    {"batches": [{"sessionId": "s", "status": "pending", "patches": "oops"}]},
    {"batches": [{"sessionId": "s", "status": "pending", "patches": ["oops"]}]},
    {"batches": [{"sessionId": "s", "status": "pending",
                  "patches": [{"fingerprint": {}, "changes": ["oops"]}]}]},
    {"batches": [{"sessionId": "s", "status": "pending",
                  "patches": [{"fingerprint": "oops", "changes": {}}]}]},
    {"batches": "oops"},
    {"batches": ["oops"]},
])
def test_malformed_containers_die_cleanly(tmp_path, doc):
    """A raw AttributeError/TypeError traceback after a half-printed listing is
    not an acceptable failure mode for a file Claude is about to act on."""
    f = write(tmp_path, doc)
    for cmd in ("pending", "status"):
        r = run(cmd, str(f))
        assert r.returncode != 0, f"{cmd} accepted a corrupt file"
        assert "corrupt edits file" in r.stderr
        assert "Traceback" not in r.stderr


def test_invalid_json_dies_cleanly(tmp_path):
    f = tmp_path / "page.webtweak.json"
    f.write_text("{not json", encoding="utf-8")
    r = run("pending", str(f))
    assert r.returncode != 0
    assert "corrupt edits file" in r.stderr
    assert "Traceback" not in r.stderr


# --- mark ------------------------------------------------------------------

def test_mark_flips_the_single_pending_batch(tmp_path):
    f = write(tmp_path, {"target": "page.html", "batches": [batch()]})
    r = run("mark", str(f))
    assert r.returncode == 0
    assert "marked 1" in r.stdout
    doc = json.loads(f.read_text())
    assert doc["batches"][0]["status"] == "reconciled"
    assert doc["batches"][0]["reconciledAt"]


def test_bare_mark_refuses_when_several_are_pending(tmp_path):
    """Reconciling one session must not silently retire another - this guard is
    the only thing standing between a skipped patch and permanent loss."""
    f = write(tmp_path, {"target": "page.html",
                         "batches": [batch("s1"), batch("s2")]})
    r = run("mark", str(f))
    assert r.returncode != 0
    doc = json.loads(f.read_text())
    assert [b["status"] for b in doc["batches"]] == ["pending", "pending"]


def test_mark_by_session_flips_only_that_batch(tmp_path):
    f = write(tmp_path, {"target": "page.html",
                         "batches": [batch("s1"), batch("s2")]})
    r = run("mark", str(f), "s2")
    assert r.returncode == 0
    doc = json.loads(f.read_text())
    assert [b["status"] for b in doc["batches"]] == ["pending", "reconciled"]


def test_mark_with_unknown_session_changes_nothing(tmp_path):
    f = write(tmp_path, {"target": "page.html", "batches": [batch("s1")]})
    r = run("mark", str(f), "nope")
    assert r.returncode != 0
    assert "nothing marked" in r.stderr
    assert json.loads(f.read_text())["batches"][0]["status"] == "pending"


def test_mark_preserves_unicode_without_escaping(tmp_path):
    """The edits file is meant to be committed in the site's repo, so mark must
    not churn every non-ASCII character into an escape on rewrite."""
    patches = [{"fingerprint": {"tag": "p", "ownText": "café — naïve 心"},
                "changes": {"color": "#333"}}]
    f = write(tmp_path, {"target": "page.html", "batches": [batch(patches=patches)]})
    assert run("mark", str(f)).returncode == 0
    raw = f.read_text(encoding="utf-8")
    assert "café — naïve 心" in raw
    assert "\\u" not in raw


def test_mark_leaves_file_untouched_on_failure(tmp_path):
    f = write(tmp_path, {"target": "page.html", "batches": [batch("s1")]})
    before = f.read_text()
    run("mark", str(f), "nope")
    assert f.read_text() == before
    assert not list(tmp_path.glob("*.tmp"))
