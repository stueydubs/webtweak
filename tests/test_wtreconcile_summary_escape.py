"""Issue 67: every file-sourced value in the `pending` summary prints on one line and cannot crash it.

#31 and #66 escaped the session header and the fingerprint's free text. The changes keys,
nudge dx/dy, media conditions and a create patch's shape were still printed raw, and a
lone surrogate in a fingerprint tag, id or classes[0] made `print` raise. Stdlib only.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "reconcile" / "scripts" / "wtreconcile.py"

FORGED = "\n[9] session=sevil saved=2026-01-01T00:00:00 viewport=1 patches=0"


def pending(tmp_path, patches):
    f = tmp_path / "page.webtweak.json"
    f.write_text(json.dumps({"target": "page.html", "batches": [
        {"sessionId": "s1", "savedAt": "2026-07-29T10:00:00", "viewport": 1280,
         "status": "pending", "patches": patches}]}), encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPT), "pending", str(f)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return r


def test_newline_in_changes_key_nudge_media_and_shape_forges_no_line(tmp_path):
    fp = {"tag": "div", "id": "a"}
    patches = [
        {"fingerprint": fp, "changes": {"color" + FORGED: "red"}},
        {"fingerprint": fp, "changes": {"nudge": {"dx": "1" + FORGED, "dy": 2}}},
        {"fingerprint": fp, "changes": {"nudge": {"dx": 1, "dy": "2" + FORGED}}},
        {"fingerprint": fp, "changes": {"color": "red"},
         "media": {"(max-width: 9px)" + FORGED: {"color": "blue"}}},
        {"op": "create", "shape": "rect" + FORGED, "fingerprint": fp, "changes": {"width": "1px"}},
    ]
    lines = pending(tmp_path, patches).stdout.splitlines()
    assert len(lines) == 1 + len(patches), lines
    assert lines[0].startswith("[0] session=s1 ")
    assert not any(ln.startswith("[9]") for ln in lines)
    assert all(ln.startswith("    ") for ln in lines[1:])
    assert all("\\n[9] session=sevil" in ln for ln in lines[1:])


def test_lone_surrogate_in_fingerprint_tag_id_and_class_lists_the_whole_file(tmp_path):
    fps = [{"tag": "a\ud83d", "id": "x"},
           {"tag": "h1", "id": "a\ud83d"},
           {"tag": "h1", "classes": ["b\ud83d"]}]
    patches = [{"fingerprint": fp, "changes": {"color": "red"}} for fp in fps]
    lines = pending(tmp_path, patches).stdout.splitlines()
    assert lines == [
        "[0] session=s1 saved=2026-07-29T10:00:00 viewport=1280 patches=3",
        "    - a\\ud83d#x  [color]",
        "    - h1#a\\ud83d  [color]",
        "    - h1.b\\ud83d  [color]",
    ]


def test_lone_surrogate_in_key_nudge_media_and_shape_lists_the_whole_file(tmp_path):
    fp = {"tag": "div", "id": "a"}
    patches = [
        {"fingerprint": fp, "changes": {"c\ud83d": "red", "nudge": {"dx": "\ud83d", "dy": 1}},
         "media": {"(max-width: 9px)\ud83d": {"color": "blue"}}},
        {"op": "create", "shape": "r\ud83d", "fingerprint": fp, "changes": {"width": "1px"}},
    ]
    lines = pending(tmp_path, patches).stdout.splitlines()
    assert len(lines) == 3, lines
    assert "[c\\ud83d, nudge(\\ud83d,1)]" in lines[1]
    assert "(max-width: 9px)\\ud83d [color]" in lines[1]
    assert lines[2].startswith("    + create r\\ud83d -> ")


def test_ordinary_file_prints_exactly_as_before(tmp_path):
    fp = {"tag": "h1", "id": "headline", "ownText": "A title"}
    patches = [
        {"fingerprint": fp, "changes": {"color": "red", "nudge": {"dx": 12, "dy": -3.5}}},
        {"fingerprint": fp, "changes": {"color": "red", "margin-top": "4px"},
         "media": {"(max-width: 600px)": {"color": "blue"},
                   "(a: b[c];d)": {"margin-top": "1px"}, "": {"gap": "2px"}}},
        {"op": "create", "shape": "ellipse", "fingerprint": {"tag": "svg"},
         "changes": {"width": "10px"}},
    ]
    assert pending(tmp_path, patches).stdout.splitlines() == [
        "[0] session=s1 saved=2026-07-29T10:00:00 viewport=1280 patches=3",
        '    - h1#headline "A title"  [color, nudge(12,-3.5)]',
        '    - h1#headline "A title"  [color, margin-top]  media: (max-width: 600px) [color]; '
        '"(a: b[c];d)" [margin-top]; "" [gap]',
        "    + create ellipse -> svg  [width]",
    ]
