#!/usr/bin/env python3
"""webtweak - a local visual editor for hand-coded HTML/CSS pages.

Opens a local source .html file in the browser with an editing Overlay, captures
what you change visually as machine-readable Patches, and writes them to a running
-history edits file (<name>.webtweak.json) next to the page. Claude then reconciles
those Patches into the real source. See CONTEXT.md and docs/adr/0001-*.

Python stdlib only. No dependencies. interact.js is vendored under overlay/.
"""

import argparse
import json
import os
import sys
import threading
import webbrowser
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
OVERLAY_DIR = TOOL_DIR / "overlay"
RESERVED = "/__webtweak__/"
MAX_BODY = 8 * 1024 * 1024  # 8 MB cap on a save payload

# Assets the Overlay loads, mapped to files in OVERLAY_DIR.
OVERLAY_ASSETS = {
    "overlay.js": "application/javascript; charset=utf-8",
    "overlay.css": "text/css; charset=utf-8",
    "interact.min.js": "application/javascript; charset=utf-8",
}


# --- pure functions (no HTTP, unit-testable) --------------------------------

def overlay_markup(target_name: str) -> str:
    """The markup injected before </body>: config object + Overlay assets."""
    cfg = json.dumps({"target": target_name})
    return (
        "\n<!-- webtweak overlay (injected, not part of source) -->\n"
        f'<script>window.__WEBTWEAK__ = {cfg};</script>\n'
        f'<link rel="stylesheet" href="{RESERVED}overlay.css">\n'
        f'<script src="{RESERVED}interact.min.js"></script>\n'
        f'<script src="{RESERVED}overlay.js" defer></script>\n'
    )


def inject_overlay(html: str, target_name: str) -> str:
    """Insert the Overlay markup immediately before the final </body>.

    Appends to the end if no </body> is present. Pure: no I/O.
    """
    markup = overlay_markup(target_name)
    idx = html.lower().rfind("</body>")
    if idx == -1:
        return html + markup
    return html[:idx] + markup + html[idx:]


def apply_batch(doc: dict, payload: dict, now: str) -> dict:
    """Fold a save payload into the running-history edits document.

    Running-history semantics: replace the matching same-session *pending*
    Batch (a clean snapshot of this session), else append a new pending Batch.
    `reconciled` Batches are never touched. Pure: returns a new-state doc,
    no I/O. `now` is the caller-supplied save timestamp.

    Defensive: a doc whose `batches` is missing or not a list is re-initialised,
    but any other top-level keys it carries are preserved.
    """
    if isinstance(doc, dict) and isinstance(doc.get("batches"), list):
        doc = dict(doc)  # preserve other top-level metadata
    else:
        doc = {"target": payload.get("target"), "batches": []}
    doc.setdefault("target", payload.get("target"))

    patches = payload.get("patches")
    if not isinstance(patches, list):
        patches = []
    session = payload.get("sessionId") or "unknown"
    batches = list(doc["batches"])

    if not patches:
        # An empty save means the user reverted every edit in this session (e.g.
        # after a reload). Drop this session's pending snapshot rather than leaving
        # a stale batch on disk that reconcile would otherwise pick up. Reconciled
        # batches are immutable and never affected.
        doc["batches"] = [
            b for b in batches
            if not (isinstance(b, dict) and b.get("sessionId") == session
                    and b.get("status") == "pending")
        ]
        return doc

    batch = {
        "sessionId": session,
        "savedAt": now,
        "viewport": payload.get("viewport"),
        "status": "pending",
        "patches": patches,
    }
    for i, b in enumerate(batches):
        if isinstance(b, dict) and b.get("sessionId") == session and b.get("status") == "pending":
            batches[i] = batch
            break
    else:
        batches.append(batch)
    doc["batches"] = batches
    return doc


def write_json_atomic(path: Path, doc: dict) -> None:
    """Write `doc` to `path` atomically: temp file in the same dir, fsync, replace.

    Path.replace is os.replace under the hood - atomic on POSIX and Windows - so a
    concurrent reader always sees either the old or the new complete file, never a
    torn one. The fsync flushes the file's data before the replace; the rename itself
    is atomic but its directory-entry update is not separately fsynced, so a power loss
    in the rename window is not guarded (acceptable for a local dev tool - the reconcile
    record is the source of truth). A failed write removes the temp file, not a stray.
    """
    tmp = path.parent / (path.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(doc, indent=2) + "\n")
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


class Handler(SimpleHTTPRequestHandler):
    # Injected by the factory in serve().
    serve_root: str = "."
    target_name: str = "index.html"
    # Serialises the edits-file read-modify-write across worker threads.
    _save_lock = threading.Lock()

    def log_message(self, fmt, *args):  # keep the console quiet but useful
        sys.stderr.write("  webtweak: " + (fmt % args) + "\n")

    def _edits_path(self) -> Path:
        stem = Path(self.target_name).stem
        return Path(self.serve_root) / f"{stem}.webtweak.json"

    # --- GET: serve files, injecting the Overlay into HTML responses ---------
    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path.startswith(RESERVED):
            name = path[len(RESERVED):]
            if name == "edits":
                return self._serve_edits()
            return self._serve_overlay_asset(name)

        local = Path(self.translate_path(self.path))
        if local.is_dir():
            local = local / "index.html"

        if local.suffix.lower() in (".html", ".htm") and local.is_file():
            return self._serve_html(local)

        return super().do_GET()  # images, css, fonts, js, etc.

    def list_directory(self, path):
        # The served root is the site source dir - don't expose listings of it
        # (which would reveal the edits file, .bak recovery files, and .tmp).
        self.send_error(404, "No listing")
        return None

    def _send_bytes(self, body: bytes, ctype: str, code: int = 200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_overlay_asset(self, name: str):
        # Explicit containment: never serve outside overlay/, regardless of the
        # whitelist. Defence-in-depth against path traversal in `name`.
        asset = OVERLAY_DIR / name
        try:
            resolved = asset.resolve()
            resolved.relative_to(OVERLAY_DIR.resolve())
        except (ValueError, OSError):
            self.send_error(404, "Unknown webtweak asset")
            return
        ctype = OVERLAY_ASSETS.get(name)
        if ctype is None or not resolved.is_file():
            self.send_error(404, "Unknown webtweak asset")
            return
        self._send_bytes(resolved.read_bytes(), ctype)

    def _serve_edits(self):
        """Return the current edits file so the Overlay can restore on reload."""
        path = self._edits_path()
        body = b'{"batches": []}'
        with Handler._save_lock:  # never read a file mid-save
            if path.is_file():
                try:
                    raw = path.read_bytes()
                    json.loads(raw)  # only hand back valid JSON; else fall back to empty
                    body = raw
                except (OSError, json.JSONDecodeError):
                    pass
        self._send_bytes(body, "application/json")

    def _serve_html(self, local: Path):
        html = local.read_text(encoding="utf-8", errors="replace")
        html = inject_overlay(html, self.target_name)
        self._send_bytes(html.encode("utf-8"), "text/html; charset=utf-8")

    # --- POST: save a pending Batch into the running-history edits file ------
    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path != RESERVED + "save":
            self.send_error(404, "Unknown webtweak endpoint")
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            self.send_error(400, "Bad Content-Length")
            return
        if length < 0 or length > MAX_BODY:
            self.send_error(413, "Payload too large")
            return
        # Bound only the body read (not the whole keep-alive connection, which would
        # time out idle sockets and log spurious errors). Restore the socket after.
        self.connection.settimeout(30)
        try:
            raw = self.rfile.read(length)
        except OSError:  # socket timeout / aborted body - don't park the thread
            self.send_error(400, "Incomplete request body")
            return
        finally:
            self.connection.settimeout(None)
        if len(raw) < length:
            self.send_error(400, "Incomplete request body")
            return
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self.send_error(400, "Bad JSON")
            return
        if not isinstance(payload, dict):
            self.send_error(400, "Bad JSON: expected an object")
            return

        try:
            result, code = self._save_batch(payload), 200
        except Exception as e:  # disk full, permissions, etc. - report, don't crash
            result, code = {"ok": False, "error": str(e)}, 500
        self._send_bytes(json.dumps(result).encode("utf-8"), "application/json", code)

    def _save_batch(self, payload: dict) -> dict:
        edits_path = self._edits_path()
        with Handler._save_lock:
            doc = None  # apply_batch builds the canonical empty doc from None
            if edits_path.is_file():
                # A read failure (OSError) is transient - let it propagate to the outer
                # 500 so a good file is never nuked; only genuine JSON corruption triggers
                # the back-up-and-start-fresh recovery.
                raw_doc = edits_path.read_text(encoding="utf-8")
                try:
                    doc = json.loads(raw_doc)
                except json.JSONDecodeError:
                    # Microsecond stamp so even same-second repeated corruption can't clobber.
                    stamp = datetime.now().strftime("%Y%m%dT%H%M%S_%f")
                    backup = edits_path.parent / (edits_path.name + "." + stamp + ".bak")
                    edits_path.replace(backup)
                    self.log_message(
                        "edits file was corrupt JSON; backed up to %s and started fresh",
                        backup.name,
                    )

            payload.setdefault("target", self.target_name)
            now = datetime.now().isoformat(timespec="seconds")
            doc = apply_batch(doc, payload, now)
            write_json_atomic(edits_path, doc)

        n = len(payload.get("patches") or [])
        self.log_message("saved %d patch(es) -> %s", n, edits_path.name)
        return {"ok": True, "file": edits_path.name, "patches": n}


def serve(target: Path, port: int, open_browser: bool):
    root = target.parent.resolve()
    # Subclass on the fly so the handler knows its root + target page.
    cls = type("BoundHandler", (Handler,), {
        "serve_root": str(root),
        "target_name": target.name,
    })
    bound = partial(cls, directory=str(root))

    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), bound)
    except OSError as e:
        sys.exit(f"webtweak: cannot bind port {port} ({e.strerror or e}). "
                 f"Try a different --port, or --port 0 for any free port.")

    actual = httpd.server_address[1]
    url = f"http://127.0.0.1:{actual}/{target.name}"
    print(f"webtweak editing: {target}")
    print(f"  serving {root}")
    # flush here so a reader (the test harness) sees readiness without waiting on later lines
    print(f"  listening on 127.0.0.1:{actual}", flush=True)
    print(f"  open    {url}")
    print("  Ctrl-C to stop.\n", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nwebtweak stopped.")
    finally:
        httpd.server_close()


def main():
    ap = argparse.ArgumentParser(description="Local visual editor for hand-coded HTML/CSS.")
    ap.add_argument("html", help="path to the local source .html file to edit")
    ap.add_argument("--port", type=int, default=8723,
                    help="port (default 8723; 0 picks any free port)")
    ap.add_argument("--no-browser", action="store_true", help="don't auto-open the browser")
    args = ap.parse_args()

    target = Path(args.html).resolve()
    if not target.is_file():
        sys.exit(f"webtweak: not a file: {target}")
    if target.suffix.lower() not in (".html", ".htm"):
        sys.exit(f"webtweak: expected an .html file, got {target.suffix or 'no extension'}")

    serve(target, args.port, not args.no_browser)


if __name__ == "__main__":
    main()
