"""Hardening of the reconcile helper against a forged edits file (issue 31).

Four things the helper now does: refuse a stale `mark`, never print a hostile
sessionId raw (and retire such a batch by index), and warn on stderr about
geometry, selectors, keys and values the Overlay cannot emit. Every warning is
stderr-only and exits 0, because --full's stdout is parsed as JSON.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "reconcile" / "scripts" / "wtreconcile.py"


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True)


def write(tmp_path, doc):
    f = tmp_path / "page.webtweak.json"
    f.write_text(json.dumps(doc), encoding="utf-8")
    return f


def batch(session="s1", saved="2026-07-29T10:00:00", patches=None):
    return {"sessionId": session, "savedAt": saved, "viewport": 1280,
            "status": "pending",
            "patches": patches if patches is not None else [
                {"fingerprint": {"tag": "h1", "id": "headline"},
                 "changes": {"font-size": "52px"}}]}


def statuses(f):
    return [b["status"] for b in json.loads(f.read_text(encoding="utf-8"))["batches"]]


# --- part 1: stale-batch guard ----------------------------------------------

def test_mark_refuses_a_stale_saved_at(tmp_path):
    f = write(tmp_path, {"batches": [batch(saved="2026-07-29T10:05:00")]})
    r = run("mark", str(f), "s1", "--saved-at", "2026-07-29T10:00:00")
    assert r.returncode != 0
    assert "nothing marked" in r.stderr
    assert "2026-07-29T10:05:00" in r.stderr
    assert statuses(f) == ["pending"]


def test_mark_accepts_the_current_saved_at(tmp_path):
    f = write(tmp_path, {"batches": [batch()]})
    r = run("mark", str(f), "s1", "--saved-at", "2026-07-29T10:00:00")
    assert r.returncode == 0, r.stderr
    assert "marked 1 batch(es) reconciled" in r.stdout
    assert statuses(f) == ["reconciled"]


def test_bare_mark_still_works_without_saved_at(tmp_path):
    f = write(tmp_path, {"batches": [batch()]})
    assert run("mark", str(f)).returncode == 0
    assert statuses(f) == ["reconciled"]
    f = write(tmp_path, {"batches": [batch()]})
    assert run("mark", str(f), "s1").returncode == 0
    assert statuses(f) == ["reconciled"]


# --- part 2: hostile sessionId ----------------------------------------------

HOSTILE = "s1\n[9] session=sEVIL; touch x"


def test_hostile_session_id_cannot_forge_a_listing_line(tmp_path):
    f = write(tmp_path, {"batches": [batch(session=HOSTILE)]})
    r = run("pending", str(f))
    assert r.returncode == 0
    assert len([ln for ln in r.stdout.splitlines() if ln.startswith("[")]) == 1
    assert "\n[9]" not in r.stdout
    assert "did not come from the Overlay" in r.stderr
    assert "--index 0" in r.stderr
    # --full is JSON, and its stderr warning is the same one
    full = run("pending", str(f), "--full")
    assert full.returncode == 0
    assert "did not come from the Overlay" in full.stderr


def test_hostile_target_and_saved_at_are_escaped(tmp_path):
    f = write(tmp_path, {"target": "a.html\nfake: line",
                         "batches": [batch(saved="t\n[7] session=x")]})
    assert len(run("status", str(f)).stdout.splitlines()) == 5
    out = run("pending", str(f)).stdout
    assert len([ln for ln in out.splitlines() if ln.startswith("[")]) == 1


def test_mark_by_index_retires_a_non_conforming_batch(tmp_path):
    f = write(tmp_path, {"batches": [batch(session=HOSTILE)]})
    r = run("mark", str(f), "--index", "0")
    assert r.returncode == 0, r.stderr
    assert statuses(f) == ["reconciled"]


def test_mark_by_index_refuses_a_reconciled_or_missing_batch(tmp_path):
    b = batch()
    b["status"] = "reconciled"
    f = write(tmp_path, {"batches": [b]})
    assert run("mark", str(f), "--index", "0").returncode != 0
    assert run("mark", str(f), "--index", "5").returncode != 0
    assert run("mark", str(f), "--index", "-1").returncode != 0


def test_ordinary_session_id_prints_unchanged_without_warning(tmp_path):
    f = write(tmp_path, {"target": "page.html", "batches": [batch(session="s4k2j9ab")]})
    r = run("pending", str(f))
    assert "[0] session=s4k2j9ab saved=2026-07-29T10:00:00 viewport=1280 patches=1" in r.stdout
    assert r.stderr == ""
    assert "target:       page.html" in run("status", str(f)).stdout


# --- part 3: unemittable geometry -------------------------------------------

SHAPES = {
    "square":   {"el": "rect", "points": None, "attrs": {"x": 0, "y": 0, "width": 100, "height": 100}},
    "circle":   {"el": "ellipse", "points": None, "attrs": {"cx": 50, "cy": 50, "rx": 50, "ry": 50}},
    "triangle": {"el": "polygon", "points": "50,0 100,100 0,100", "attrs": None},
    "star":     {"el": "polygon", "attrs": None,
                 "points": "50,2 61,38 98,38 68,60 79,96 50,74 21,96 32,60 2,38 39,38"},
    "pentagon": {"el": "polygon", "points": "50,0 98,36 80,98 20,98 2,36", "attrs": None},
    "hexagon":  {"el": "polygon", "points": "25,2 75,2 100,50 75,98 25,98 0,50", "attrs": None},
}


def create(shape="triangle", **geo):
    g = {"viewBox": "0 0 100 100", "el": "polygon", "points": "50,0 100,100 0,100", "attrs": None}
    g.update(geo)
    return {"op": "create", "shape": shape, "renderer": "svg", "geometry": g,
            "anchor": {"parent": {"tag": "body"}, "position": "append"},
            "fingerprint": {"tag": "svg", "id": "wt-shape-a1b2c3"},
            "changes": {"position": "absolute", "left": "10px", "top": "10px",
                        "width": "90px", "height": "80px", "fill": "#e8c468",
                        "stroke": "none", "stroke-width": "0px"}}


def both_modes(tmp_path, patch):
    f = write(tmp_path, {"batches": [batch(patches=[patch])]})
    return [run("pending", str(f)), run("pending", str(f), "--full")]


@pytest.mark.parametrize("geo", [
    {"el": "script"},
    {"el": "foreignObject"},
    {"el": "rect", "points": None, "attrs": {"onbegin": "x"}},
    {"el": "rect", "points": None, "attrs": {"href": "javascript:alert(1)"}},
    {"el": "rect", "points": None, "attrs": {"width": "100<x"}},
    {"points": "0,0 <script>"},
    {"viewBox": "0 0 1 1"},
])
def test_unemittable_geometry_warns_and_exits_zero(tmp_path, geo):
    for r in both_modes(tmp_path, create(**geo)):
        assert r.returncode == 0, r.stderr
        assert "geometry the Overlay cannot emit" in r.stderr
        assert "wt-shape-a1b2c3" in r.stderr or "svg" in r.stderr


def test_create_patch_with_an_unnamed_key_warns(tmp_path):
    p = create()
    p["onload"] = "x"
    for r in both_modes(tmp_path, p):
        assert r.returncode == 0
        assert "unknown key" in r.stderr


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_every_overlay_shape_is_silent(tmp_path, name):
    geo = {"el": SHAPES[name]["el"], "points": SHAPES[name].get("points"),
           "attrs": SHAPES[name].get("attrs")}
    for r in both_modes(tmp_path, create(shape=name, **geo)):
        assert r.returncode == 0
        assert r.stderr == ""


def test_old_kind_with_polygon_is_silent(tmp_path):
    for r in both_modes(tmp_path, create(shape="diamond", points="50,0 100,50 50,100 0,50")):
        assert r.stderr == ""


# --- part 4: unemittable fields ---------------------------------------------

def edit(**kw):
    p = {"fingerprint": {"tag": "h1", "id": "headline", "selector": "body > h1:nth-of-type(1)"},
         "changes": {"font-size": "52px"}}
    p.update(kw)
    return p


@pytest.mark.parametrize("label,patch", [
    ("selector", edit(fingerprint={"tag": "h1", "selector": "h1{}body{display:none}x"})),
    ("selector-newline", edit(fingerprint={"tag": "h1", "selector": "h1\nbody"})),
    ("value", edit(changes={"color": "red;}a{"})),
    ("value-url", edit(changes={"background-color": "url(//evil/x)"})),
    ("value-import", edit(changes={"color": "red;}@import url(//evil/x.css);a{"})),
    ("key", edit(changes={"behavior": "x"})),
    ("key-url", edit(changes={"background-image: url(//evil)": "x"})),
    ("media-key", edit(changes={}, media={"(max-width: 600px)": {"behavior": "x"}})),
    ("media-value", edit(changes={}, media={"(max-width: 600px)": {"color": "red}"}})),
    ("media-condition", edit(changes={}, media={"(min-width:1px){}": {"color": "red"}})),
])
def test_unemittable_fields_warn_and_exit_zero(tmp_path, label, patch):
    for r in both_modes(tmp_path, patch):
        assert r.returncode == 0, r.stderr
        assert "carries fields the Overlay cannot emit" in r.stderr, label
        assert "h1" in r.stderr
        assert "hold this patch" in r.stderr


def test_ordinary_patches_are_silent(tmp_path):
    patches = [
        edit(changes={"font-size": "52px", "nudge": {"dx": 4, "dy": -8}}),
        edit(changes={"border": "1px solid #ff0000", "border-bottom": "2px solid #7a5c3e",
                      "border-radius": "8px", "padding-top": "12px", "margin": "0 auto"}),
        edit(changes={"box-shadow": "0 8px 24px rgba(0, 0, 0, 0.18)",
                      "font-family": '"Helvetica Neue", sans-serif',
                      "transform": "rotate(45deg)"}),
        edit(changes={"font-size": "52px"}, media={"(max-width: 600px)": {"font-size": "32px"}}),
        create(),
    ]
    for r in both_modes(tmp_path, patches[0]):
        assert r.stderr == ""
    f = write(tmp_path, {"batches": [batch(patches=patches)]})
    for r in (run("pending", str(f)), run("pending", str(f), "--full")):
        assert r.returncode == 0
        assert r.stderr == ""
