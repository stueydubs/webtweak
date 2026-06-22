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


def start(page):
    """Launch webtweak on an ephemeral port; return (proc, port).

    Reads the bound port back from the server's `listening on 127.0.0.1:<port>`
    stdout line, and fails fast (surfacing stderr) if the process dies first.
    """
    proc = subprocess.Popen(
        ["python3", str(ROOT / "webtweak"), str(page), "--port", "0", "--no-browser"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
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


def make_page():
    """Copy the sample fixture into a fresh temp dir; return (tmp_dir, page_path)."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    page = tmp / "sample.html"
    shutil.copy(ROOT / "fixtures" / "sample.html", page)
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
