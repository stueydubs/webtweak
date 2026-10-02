"""Hardening of the edits-file writers (wtreconcile `_save`, the server's save).

Covers lone surrogates from the Overlay's UTF-16 text truncation, null containers
that `_load` lets through, the UTC `reconciledAt` stamp, exclusive temp-file
creation (a planted symlink must not be followed) and `_save`'s failure cleanup.
Stdlib only.
"""

import http.client
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from _server import make_page, start, stop

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "reconcile" / "scripts" / "wtreconcile.py"


def run(*args, env=None):
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, env=env)


def write(tmp_path, doc):
    f = tmp_path / "page.webtweak.json"
    f.write_text(json.dumps(doc), encoding="utf-8")
    return f


def batch(session="s1", **over):
    b = {"sessionId": session, "savedAt": "2026-07-29T10:00:00", "viewport": 1280,
         "status": "pending",
         "patches": [{"fingerprint": {"tag": "h1", "id": "headline"},
                      "changes": {"font-size": "52px"}}]}
    b.update(over)
    return b


def load_module():
    spec = importlib.util.spec_from_file_location("wtreconcile_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- lone surrogates ---------------------------------------------------------

def _surrogate_file(tmp_path):
    # Raw text, not json.dumps(): the server stores the escape JSON.stringify emitted.
    f = tmp_path / "page.webtweak.json"
    f.write_text(
        '{"target": "page.html", "batches": [{"sessionId": "s1", "status": "pending", '
        '"savedAt": "2026-07-29T10:00:00", "patches": [{"fingerprint": '
        '{"tag": "p", "text": "a\\ud83d"}, "changes": {"color": "red"}}]}]}',
        encoding="ascii")
    return f


def test_mark_survives_a_lone_surrogate(tmp_path):
    f = _surrogate_file(tmp_path)
    r = run("mark", str(f))
    assert r.returncode == 0, r.stderr
    raw = f.read_text(encoding="utf-8")
    doc = json.loads(raw)  # still valid JSON
    assert doc["batches"][0]["status"] == "reconciled"
    assert "\\ud83d" in raw  # written back as the escape it arrived as
    assert not list(tmp_path.glob("*.tmp"))


def test_pending_survives_a_lone_surrogate(tmp_path):
    f = _surrogate_file(tmp_path)
    r = run("pending", str(f))
    assert r.returncode == 0, r.stderr
    assert "Traceback" not in r.stderr
    assert "\\ud83d" in r.stdout


# --- null containers ---------------------------------------------------------

NULL_SHAPES = {
    "batches": {"target": "page.html", "batches": None},
    "patches": {"target": "page.html", "batches": [batch(patches=None)]},
    "fingerprint": {"target": "page.html", "batches": [batch(patches=[
        {"fingerprint": None, "changes": {"color": "red"}}])]},
}


@pytest.mark.parametrize("shape", sorted(NULL_SHAPES))
@pytest.mark.parametrize("cmd", [("pending",), ("pending", "--full"), ("status",)])
def test_read_commands_accept_null_containers(tmp_path, shape, cmd):
    f = write(tmp_path, NULL_SHAPES[shape])
    r = run(cmd[0], str(f), *cmd[1:])
    assert "Traceback" not in r.stderr
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("shape", sorted(NULL_SHAPES))
def test_mark_agrees_with_pending_on_null_containers(tmp_path, shape):
    f = write(tmp_path, NULL_SHAPES[shape])
    pend = run("pending", str(f))
    r = run("mark", str(f))
    assert "Traceback" not in r.stderr
    # `batches: null` has nothing to mark (clean refusal); the others retire the batch.
    assert r.returncode == (1 if shape == "batches" else 0), r.stderr
    assert pend.returncode == 0


# --- reconciledAt is UTC -----------------------------------------------------

def test_reconciled_at_is_utc_whatever_the_local_zone(tmp_path):
    f = write(tmp_path, {"target": "page.html", "batches": [batch()]})
    env = dict(os.environ, TZ="Australia/Perth")
    before = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    assert run("mark", str(f), env=env).returncode == 0
    after = datetime.now(timezone.utc).replace(tzinfo=None)
    stamp = json.loads(f.read_text(encoding="utf-8"))["batches"][0]["reconciledAt"]
    assert len(stamp) == len("2026-07-29T10:00:00") and "+" not in stamp
    got = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S")
    # Perth is UTC+8: a local-time stamp would be hours off, not seconds.
    assert -2 <= (got - before).total_seconds() <= (after - before).total_seconds() + 2


# --- exclusive temp file -----------------------------------------------------

def test_mark_does_not_follow_a_planted_tmp_symlink(tmp_path):
    f = write(tmp_path, {"target": "page.html", "batches": [batch()]})
    victim = tmp_path / "victim.txt"
    victim.write_bytes(b"do not touch\n")
    try:
        (tmp_path / "page.webtweak.json.tmp").symlink_to(victim)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    r = run("mark", str(f))
    assert r.returncode == 0, r.stderr
    assert victim.read_bytes() == b"do not touch\n"
    assert json.loads(f.read_text(encoding="utf-8"))["batches"][0]["status"] == "reconciled"
    assert not list(tmp_path.glob("*.tmp"))


def test_server_save_replaces_a_stale_pid_tmp_and_ignores_a_symlink():
    tmp, page = make_page()
    proc, port = start(page)
    try:
        edits = tmp / "sample.webtweak.json"
        stale = tmp / f"sample.webtweak.json.{proc.pid}.tmp"
        stale.write_text("stale half-written file")
        body = json.dumps({"sessionId": "s1", "patches": [
            {"fingerprint": {"tag": "h1"}, "changes": {"color": "red"}}]})

        def save():
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            conn.request("POST", "/__webtweak__/save", body=body,
                         headers={"Content-Type": "application/json"})
            status = conn.getresponse().status
            conn.close()
            return status

        assert save() == 200
        assert json.loads(edits.read_text(encoding="utf-8"))["batches"]
        assert not stale.exists()

        victim = tmp / "victim.txt"
        victim.write_bytes(b"do not touch\n")
        try:
            stale.symlink_to(victim)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks unavailable")
        assert save() == 200
        assert victim.read_bytes() == b"do not touch\n"
    finally:
        stop(proc)
        shutil.rmtree(tmp, ignore_errors=True)


# --- _save failure cleanup and atomic replace --------------------------------

@pytest.mark.parametrize("target", ["fsync", "replace"])
def test_save_failure_leaves_original_and_no_tmp(tmp_path, monkeypatch, target):
    mod = load_module()
    f = write(tmp_path, {"target": "page.html", "batches": [batch()]})
    before = f.read_bytes()

    def boom(*a, **k):
        raise OSError("injected")

    if target == "fsync":
        monkeypatch.setattr(mod.os, "fsync", boom)
    else:
        monkeypatch.setattr(mod.Path, "replace", boom)
    with pytest.raises(OSError, match="injected"):
        mod._save(str(f), {"changed": True})
    assert f.read_bytes() == before
    assert not (tmp_path / "page.webtweak.json.tmp").exists()


def test_save_writes_via_replace_and_leaves_no_tmp(tmp_path):
    mod = load_module()
    f = write(tmp_path, {"target": "page.html", "batches": [batch()]})
    mod._save(str(f), {"changed": True})
    assert json.loads(f.read_text(encoding="utf-8")) == {"changed": True}
    assert not list(tmp_path.glob("*.tmp"))
