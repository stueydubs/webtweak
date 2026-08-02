"""Shared test helpers: boot the webtweak CLI and stage isolated page copies.

Stdlib only - importing this does not pull in Playwright, so the stdlib-only
integration suite and the optional browser suite both use it without coupling.
"""

import pathlib
import re
import shutil
import subprocess
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent


def start(page, root=None):
    """Launch webtweak on an ephemeral port; return (proc, port).

    Reads the bound port back from the server's `listening on 127.0.0.1:<port>`
    stdout line, and fails fast (surfacing stderr) if the process dies first.
    Pass `root` to exercise --root (serving a web root above the page).
    """
    cmd = ["node", str(ROOT / "webtweak.js"), str(page), "--port", "0", "--no-browser"]
    if root is not None:
        cmd += ["--root", str(root)]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if line == "":  # stdout EOF only happens once the child exits
            proc.wait(timeout=2)
            raise RuntimeError("webtweak exited before announcing a port:\n" + proc.stderr.read())
        m = re.search(r"listening on 127\.0\.0\.1:(\d+)", line)
        if m:
            return proc, int(m.group(1))
    raise RuntimeError("webtweak did not announce a listening port within 5s")


def make_page(name="sample.html"):
    """Copy a fixture into a fresh temp dir; return (tmp_dir, page_path).

    `name` picks which fixture - the edits file is written beside the page, so each
    test still gets its own copy whichever one it asks for.
    """
    tmp = pathlib.Path(tempfile.mkdtemp())
    page = tmp / name
    shutil.copy(ROOT / "fixtures" / name, page)
    return tmp, page


def stop(proc):
    proc.terminate()
    try:
        # communicate() drains stdout+stderr while waiting, so a child that filled
        # its stderr pipe can't deadlock on write; it also closes the pipes for us.
        proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
