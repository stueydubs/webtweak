"""Drive the pure functions of the SHIPPED implementation (webtweak.js) from Python.

The npm package ships webtweak.js; that is the code users actually run. These
helpers require it as a Node module and call its pure functions, so the unit
tests assert against the shipped behaviour rather than a parallel reference.

Each call spawns node (~30ms). That is cheap enough for a suite this size and
keeps the tests free of any JS test runner.
"""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "webtweak.js"


def _call(fn: str, args: list):
    """Invoke webtweak.js's exported `fn` with JSON args, return its JSON result."""
    script = (
        "const wt = require(process.argv[1]);"
        "const args = JSON.parse(process.argv[2]);"
        f"const out = wt[{json.dumps(fn)}](...args);"
        "process.stdout.write(JSON.stringify(out === undefined ? null : out));"
    )
    proc = subprocess.run(
        ["node", "-e", script, str(ENTRY), json.dumps(args)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise AssertionError(f"node call to {fn}() failed:\n{proc.stderr}")
    return json.loads(proc.stdout)


def inject_overlay(html: str, target_name: str) -> str:
    return _call("injectOverlay", [html, target_name])


def overlay_markup(target_name: str) -> str:
    return _call("overlayMarkup", [target_name])


def apply_batch(doc, payload, now: str):
    return _call("applyBatch", [doc, payload, now])
