"""Issue 66: `pending` must print a fingerprint's id, classes[0], ownText and tag on one line.

`_describe` builds the per-patch summary line from fingerprint fields in an edits file
that any page script can forge. A newline in one of them used to fake an extra output
line (here, a `[9] session=` batch header). Stdlib only.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "reconcile" / "scripts" / "wtreconcile.py"

FORGED = "\n[9] session=sevil saved=2026-01-01T00:00:00 viewport=1 patches=0"


def pending(tmp_path, fingerprints):
    f = tmp_path / "page.webtweak.json"
    patches = [{"fingerprint": fp, "changes": {"color": "red"}} for fp in fingerprints]
    f.write_text(json.dumps({"target": "page.html", "batches": [
        {"sessionId": "s1", "savedAt": "2026-07-29T10:00:00", "viewport": 1280,
         "status": "pending", "patches": patches}]}), encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPT), "pending", str(f)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return r


def test_newline_in_fingerprint_fields_forges_no_line(tmp_path):
    fps = [{"tag": "h1", "id": "a" + FORGED},
           {"tag": "h1", "classes": ["b" + FORGED]},
           {"tag": "h1", "ownText": "c" + FORGED},
           {"tag": "h1" + FORGED, "id": "d"}]
    lines = pending(tmp_path, fps).stdout.splitlines()
    # One batch header plus one line per patch, and nothing else.
    assert len(lines) == 1 + len(fps), lines
    assert lines[0].startswith("[0] session=s1 ")
    assert not any(ln.startswith("[9]") for ln in lines)
    assert all(ln.startswith("    - ") for ln in lines[1:])
    assert "\\n[9] session=sevil" in lines[1]


def test_carriage_return_and_other_control_characters_are_escaped(tmp_path):
    fp = {"tag": "p", "id": "x\r\x1b[2J\x85 y"}
    lines = pending(tmp_path, [fp]).stdout.splitlines()
    assert len(lines) == 2, lines
    assert "x\\r\\x1b[2J\\x85\\u2028y" in lines[1]


def test_ordinary_fingerprints_print_byte_for_byte_as_before(tmp_path):
    fps = [{"tag": "h1", "id": "headline", "ownText": "It's a \"quoted\" café title"},
           {"tag": "p", "classes": ["lead", "big"], "text": "  " + "z" * 60 + "  "},
           {"tag": "span", "ownText": "lone \ud83d surrogate"}]
    out = pending(tmp_path, fps).stdout
    assert out.splitlines()[1:] == [
        '    - h1#headline "It\'s a "quoted" café title"  [color]',
        '    - p.lead "' + "z" * 40 + '"  [color]',
        '    - span "lone \\ud83d surrogate"  [color]',
    ]
