#!/usr/bin/env python3
"""Helpers for the webtweak-reconcile skill.

Deterministic bookkeeping over a <page>.webtweak.json edits file so Claude
doesn't hand-edit JSON: list pending batches, mark batches reconciled, and
report status. Python stdlib only.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import NoReturn


def _die(msg: str) -> NoReturn:
    sys.stderr.write(f"wtreconcile: {msg}\n")
    raise SystemExit(1)


def _load(path: str) -> dict:
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        _die(f"{path} not found")
    except json.JSONDecodeError as e:
        _die(f"{path} is not valid JSON (corrupt edits file): {e}")
    except OSError as e:
        _die(f"cannot read {path}: {e}")
    # Guard the shape the way the server's apply_batch does, so a valid-JSON-but-wrong
    # structure dies cleanly instead of as a raw AttributeError mid-iteration.
    if not isinstance(doc, dict):
        _die(f"{path} is not a JSON object (corrupt edits file)")
    batches = doc.get("batches")
    if batches is not None and (not isinstance(batches, list)
                                or any(not isinstance(b, dict) for b in batches)):
        _die(f"{path} has a malformed batches array (corrupt edits file)")
    return doc


def _save(path: str, doc: dict) -> None:
    # Atomic + flushed: temp file in the same dir, fsync, then replace - so an
    # interrupted mark never truncates the edits file (it has no .bak fallback here).
    p = Path(path)
    tmp = p.parent / (p.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(doc, indent=2) + "\n")
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(p)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _changes_summary(changes: dict) -> str:
    parts = []
    for k, v in changes.items():
        if k == "nudge" and isinstance(v, dict):
            parts.append(f"nudge({v.get('dx')},{v.get('dy')})")  # surface drag magnitude
        else:
            parts.append(k)
    return ", ".join(parts)


def _describe(fp: dict) -> str:
    s = fp.get("tag", "?")
    if fp.get("id"):
        s += "#" + fp["id"]
    elif fp.get("classes"):
        s += "." + fp["classes"][0]
    text = (fp.get("ownText") or fp.get("text") or "").strip()
    if text:
        s += f' "{text[:40]}"'
    return s


def pending(args) -> None:
    doc = _load(args.file)
    pend = [(i, b) for i, b in enumerate(doc.get("batches", []))
            if b.get("status") == "pending"]

    if args.full:  # full patch JSON (fingerprints + changes) for deep work
        out = [
            {"index": i, "sessionId": b.get("sessionId"), "savedAt": b.get("savedAt"),
             "viewport": b.get("viewport"), "patchCount": len(b.get("patches", [])),
             "patches": b.get("patches", [])}
            for i, b in pend
        ]
        json.dump(out, sys.stdout, indent=2)
        print()
        return

    if not pend:
        print("no pending batches")
        return
    for i, b in pend:  # cheap orientation summary (read the file itself for full fingerprints)
        patches = b.get("patches", [])
        print(f"[{i}] session={b.get('sessionId')} saved={b.get('savedAt')} "
              f"viewport={b.get('viewport')} patches={len(patches)}")
        for p in patches:
            print(f"    - {_describe(p.get('fingerprint', {}))}  [{_changes_summary(p.get('changes') or {})}]")


def mark(args) -> None:
    doc = _load(args.file)
    now = datetime.now().isoformat(timespec="seconds")
    candidates = [
        b for b in doc.get("batches", [])
        if b.get("status") == "pending"
        and (args.session is None or b.get("sessionId") == args.session)
    ]

    if not candidates:
        if args.session is not None:
            _die(f"no pending batch with sessionId '{args.session}' - nothing marked")
        _die("no pending batches to mark")

    # Refuse to bulk-retire multiple sessions on a bare `mark`: each pending batch is a
    # separate session that may not have been reconciled yet, and marking it loses it.
    if args.session is None and len(candidates) > 1:
        ids = ", ".join(str(b.get("sessionId") or "?") for b in candidates)
        _die(f"{len(candidates)} pending batches ({ids}); pass a sessionId to mark one "
             f"at a time - reconcile each before marking it")

    for b in candidates:
        b["status"] = "reconciled"
        b["reconciledAt"] = now

    _save(args.file, doc)
    print(f"marked {len(candidates)} batch(es) reconciled")


def status(args) -> None:
    doc = _load(args.file)
    batches = doc.get("batches", [])
    pend = [b for b in batches if b.get("status") == "pending"]
    recon = [b for b in batches if b.get("status") == "reconciled"]
    last_pending = max((b.get("savedAt") or "" for b in pend), default="")
    print(f"target:       {doc.get('target')}")
    print(f"pending:      {len(pend)}")
    print(f"reconciled:   {len(recon)}")
    print(f"last pending: {last_pending or '-'}")
    print("fully reconciled" if not pend else f"{len(pend)} batch(es) awaiting reconcile")


def main() -> None:
    ap = argparse.ArgumentParser(description="webtweak-reconcile helpers")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("pending", help="list pending batches (summary; --full for patch JSON)")
    p.add_argument("file")
    p.add_argument("--full", action="store_true", help="dump full patch JSON, not a summary")
    p.set_defaults(fn=pending)

    m = sub.add_parser("mark", help="mark pending batch(es) reconciled")
    m.add_argument("file")
    m.add_argument("session", nargs="?", default=None,
                   help="sessionId to mark (all pending if omitted)")
    m.set_defaults(fn=mark)

    s = sub.add_parser("status", help="report pending vs reconciled counts")
    s.add_argument("file")
    s.set_defaults(fn=status)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
