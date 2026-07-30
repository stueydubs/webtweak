"""Structural guard: every browser test must carry the `browser` marker.

CI selects browser tests by marker, not by filename - because it once selected by
filename and three later browser modules were excluded from every job, reading
green while never executing.

The marker is supplied by importing `_browser`, so the check is simply: a module
that needs a real browser must get its gate from there. This test runs in the
stdlib job (no Playwright), which is exactly where a mis-marked module would
otherwise sneak in, hit its own `importorskip`, and be counted as a pass.
"""

import ast
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
BROWSER_HINTS = ("playwright", "sync_playwright", "chromium")


def module_files():
    # Skip this file: it names the browser hints in order to search for them, so
    # it would always look like a browser module to its own check.
    me = Path(__file__).name
    return sorted(p for p in TESTS.glob("test_*.py") if p.name != me)


def imported_names(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
            names.update(a.name for a in node.names)
    return names


@pytest.mark.parametrize("path", module_files(), ids=lambda p: p.name)
def test_browser_modules_get_their_gate_from_browser_helper(path):
    """A module that drives a browser must `from _browser import ...`.

    That single import supplies the skip-if-absent gate, `sync_playwright`, and
    the `browser` marker together - so none of the three can be forgotten
    individually, which is how the original CI gap happened.
    """
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = imported_names(tree)

    needs_browser = any(h in src for h in BROWSER_HINTS)
    gets_gate = "_browser" in names or "sync_playwright" in names

    if needs_browser:
        assert "_browser" in names, (
            f"{path.name} references a browser but does not import _browser, so it "
            f"carries no `browser` marker - CI would run it in the wrong job, where "
            f"it skips silently and counts as green."
        )
    else:
        assert not gets_gate, (
            f"{path.name} imports the browser gate but never uses a browser; that "
            f"marks it `browser` and hides it from the stdlib job."
        )


def test_at_least_one_browser_module_exists():
    """Guards the guard: if the marker were dropped everywhere, the parametrised
    test above would vacuously pass on an empty set."""
    marked = [p for p in module_files()
              if "_browser" in imported_names(ast.parse(p.read_text(encoding="utf-8")))]
    assert marked, "no browser-marked modules found - CI's `-m browser` job would collect nothing"
