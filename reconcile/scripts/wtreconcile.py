#!/usr/bin/env python3
"""Helpers for the webtweak-reconcile skill.

Deterministic bookkeeping over a <page>.webtweak.json edits file so Claude
doesn't hand-edit JSON: list pending batches, mark batches reconciled, and
report status. Python stdlib only.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn


def _die(msg: str) -> NoReturn:
    sys.stderr.write(f"wtreconcile: {msg}\n")
    raise SystemExit(1)


def _corrupt(path: str, label: str) -> NoReturn:
    # One phrasing for every shape guard below. The guards' *conditions* genuinely
    # differ (list-of-dicts vs dict vs dict-of-dicts), but the message did not, and
    # `test_malformed_containers_die_cleanly` greps a substring of it - so a typo in
    # any one hand-typed copy would have diverged silently.
    _die(f"{path} has a malformed {label} (corrupt edits file)")


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
        _corrupt(path, "batches array")
    # One level deeper: without this, a malformed patches/changes container printed
    # a partial listing and then died with a raw traceback, and `status`/`--full`
    # disagreed with `pending` about whether the same file was corrupt at all.
    for b in batches or []:
        patches = b.get("patches")
        if patches is None:
            continue
        if not isinstance(patches, list) or any(not isinstance(p, dict) for p in patches):
            _corrupt(path, "patches array")
        for p in patches:
            changes = p.get("changes")
            if changes is not None and not isinstance(changes, dict):
                _corrupt(path, "changes object")
            fp = p.get("fingerprint")
            if fp is not None and not isinstance(fp, dict):
                _corrupt(path, "fingerprint object")
            media = p.get("media")
            if media is not None and (not isinstance(media, dict)
                                      or any(not isinstance(g, dict) for g in media.values())):
                _corrupt(path, "media object")
    return doc


def _save(path: str, doc: dict) -> None:
    # Atomic + flushed: temp file in the same dir, fsync, then replace - so an
    # interrupted mark never truncates the edits file (it has no .bak fallback here).
    p = Path(path)
    tmp = p.parent / (p.name + ".tmp")
    # Clear a stale temp, then open exclusively ('x' is O_EXCL, which never follows a
    # symlink): a committed `<name>.tmp` symlink in a cloned site repo must not turn
    # this write into an overwrite of whatever it points at.
    tmp.unlink(missing_ok=True)
    try:
        with open(tmp, "x", encoding="utf-8") as f:
            # ensure_ascii=False to match what the server writes (JSON.stringify
            # emits raw UTF-8). Escaping here would rewrite every non-ASCII
            # character on each mark, churning the diff in the site's own repo.
            # The one exception is a lone surrogate (the Overlay's UTF-16 slice can
            # split an astral character): it cannot be encoded as UTF-8, so it is
            # written back as the \udXXXX escape it arrived as.
            text = json.dumps(doc, indent=2, ensure_ascii=False)
            f.write(re.sub("[\ud800-\udfff]", lambda m: f"\\u{ord(m.group()):04x}", text) + "\n")
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
            parts.append(_flat(f"nudge({v.get('dx')},{v.get('dy')})"))  # surface drag magnitude
        else:
            parts.append(_flat(k))
    return ", ".join(parts)


def _fmt_condition(cond: str) -> str:
    # A media condition is free text: the Scope picker accepts a hand-typed one, and
    # a page's own `conditionText` round-trips verbatim. This summary is a delimited
    # format - groups joined by "; ", properties wrapped in "[...]" - and CSS MQ4's
    # <general-enclosed> lets both delimiters survive inside parens. So
    # `(max-width: 9px) or (foo: a[b];c)` is one condition that would otherwise print
    # as two groups with a property list that was never there: a plausible-looking
    # wrong reading, which is the failure mode this codebase keeps re-learning.
    # Quote only when a delimiter is actually present, so every real condition stays
    # unquoted and readable. An empty/blank condition is quoted too - otherwise it
    # prints as a gap in the line and reads as a rendering fault rather than as what
    # it is, a group whose condition went missing.
    quote = not cond.strip() or any(c in cond for c in ';[]"')
    cond = _flat(cond)
    return f'"{cond}"' if quote else cond


def _media_summary(media: dict) -> str:
    # One group per condition (ADR-0004) - a patch that is media-only (no base
    # changes) must still read as real work, not a no-op `[]`.
    return "; ".join(f"{_fmt_condition(cond)} [{_changes_summary(props)}]"
                     for cond, props in media.items())


def _unbanded_summary(changes: dict, media: dict) -> str:
    # SKILL.md step 6 asks the responsiveness question per DECLARATION, not per
    # patch: one patch routinely carries an un-banded resize (every drag and grip
    # gesture records to base regardless of the selected band) alongside an unrelated
    # banded edit, and only the un-banded half can still break mobile. Which base
    # properties have no counterpart in any band is a set difference - mechanical, so
    # the script does it rather than leaving Claude to re-derive it by eye across
    # several conditions. That eyeballing is what read step 6 at the wrong
    # granularity once already.
    banded = {prop for group in media.values() for prop in group}
    return _changes_summary({k: v for k, v in changes.items() if k not in banded})


def _str(v) -> str:
    """A fingerprint scalar as text, whatever type it actually arrived as.

    `_load`'s guards check container shapes, not the scalars inside a fingerprint, and
    the edits file is committed in the user's own site repo - so it is hand-editable and
    merge-conflict-prone. A `"id": 123` or `"ownText": 42` used to reach `_describe` and
    raise mid-listing (`TypeError: can only concatenate str`), which is exactly the
    "printed a partial listing and then died with a raw traceback" failure the guard
    comment in `_load` says it exists to prevent. Worse, `status`, `pending --full` and
    `mark` all accepted the same file, so `mark` could retire a batch whose `pending`
    had crashed. Coercing keeps every subcommand's verdict on a given file the same.
    """
    return v if isinstance(v, str) else ("" if v is None else str(v))


# Every sessionId the Overlay generates is 's' + up to 8 base36 characters. Anything
# else did not come from the Overlay (any script in the served page can POST one).
_SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}\Z")
# savedAt is an ISO timestamp and target is a path, so they need a wider alphabet.
# What every pattern here excludes is what matters: newlines and control characters.
_STAMP_RE = re.compile(r"^[A-Za-z0-9_:.+-]{1,40}\Z")
_PLAIN_RE = re.compile(r"^[^\x00-\x1f\x7f-\x9f\u2028\u2029]{1,80}\Z")
_TARGET_RE = re.compile(r"^[A-Za-z0-9_./\\ -]{1,120}\Z")


def _quote(v, limit: int = 60) -> str:
    """A hostile value inside a warning: always repr(), always truncated."""
    return repr(v if isinstance(v, (str, int, float, list)) else _str(v))[:limit]


def _term(v, pattern=_SESSION_RE, limit: int = 40) -> str:
    """Render a file-sourced scalar for the terminal Claude reads.

    The edits file is attacker-writable, and this output is read as a listing and then
    quoted back onto a command line. A value that fits the shape the Overlay could have
    produced prints unchanged; anything else prints as a truncated repr(), which
    escapes newlines and control characters so it cannot forge a second output line.
    """
    s = _str(v)
    if pattern.match(s):
        return s
    return repr(s)[:limit]


_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")


def _flat(v) -> str:
    """A file-sourced field on one line: control characters print as their repr() escape.

    A lone surrogate prints as its `\\udXXX` escape too, so `print` cannot raise on it.

    Unlike `_term` this leaves an ordinary value, quotes and spaces included, untouched,
    because a fingerprint is free text rather than a fixed-shape token.
    """
    s = _CONTROL_RE.sub(lambda m: repr(m.group())[1:-1], _str(v))
    return s.encode("utf-8", "backslashreplace").decode("utf-8")


def _describe(fp: dict) -> str:
    s = _flat(fp.get("tag")) or "?"
    if fp.get("id"):
        s += "#" + _flat(fp["id"])
    elif isinstance(fp.get("classes"), list) and fp["classes"]:
        s += "." + _flat(fp["classes"][0])
    text = (_str(fp.get("ownText")) or _str(fp.get("text"))).strip()
    if text:
        # backslashreplace: a lone surrogate (from a truncated astral character) would
        # otherwise make print() raise UnicodeEncodeError mid-listing.
        s += ' "' + _flat(text[:40]).encode("utf-8", "backslashreplace").decode("utf-8") + '"'
    return s


def _warn_impossible_media(pend: list) -> None:
    # Every shape control is base-only in the Overlay, so a create patch has no way
    # to record a band - one carrying `media` did not come from webtweak. The summary
    # marks it `media?!` inline (locality), but --full dumps patches verbatim and
    # SKILL.md sends Claude there for deep work, so the anomaly also needs a channel
    # both modes share. stderr, not stdout: --full's stdout is parsed as JSON.
    # Warn, never _die - the patch is structurally fine and dying here would make the
    # whole file unreadable over one anomaly, including unrelated pending batches.
    for i, b in pend:
        for p in b.get("patches") or []:
            if p.get("op") == "create" and p.get("media"):
                sys.stderr.write(
                    f"wtreconcile: batch [{i}] has a create patch carrying `media` "
                    f"({_describe(p.get('fingerprint') or {})}) - a shape cannot record a "
                    f"band, so this did not come from webtweak; ask before reconciling\n")


_CREATE_FIELDS = {"op", "fingerprint", "changes", "media", "shape", "renderer", "geometry", "anchor"}
_SHAPE_ELS = {"rect", "ellipse", "polygon"}
_SHAPE_ATTRS = {"rx", "ry", "cx", "cy", "r", "x", "y", "width", "height"}
_POINTS_RE = re.compile(r"^[0-9 ,.%-]*\Z")
_ATTR_VALUE_RE = re.compile(r"^[0-9 ,.%-]*(?:px|em)?\Z")


def _patch_label(i, n: int, p: dict) -> str:
    return f"batch [{i}] patch {n} ({_term(_describe(p.get('fingerprint') or {}), _PLAIN_RE, 80)})"


def _warn_unemittable_geometry(pend: list) -> None:
    # SKILL.md tells Claude to copy a create patch's geometry into real source as an
    # SVG child, and a forged patch can name `script`, `foreignObject` or `set` there,
    # or an `onbegin`/`href: javascript:` attribute - markup that would ship to
    # production. The Overlay only ever emits what its SHAPES table holds, so anything
    # else did not come from webtweak. Warn, never _die, for the same reason as
    # _warn_impossible_media.
    for i, b in pend:
        for n, p in enumerate(b.get("patches") or []):
            if p.get("op") != "create":
                continue
            why = []
            extra = sorted(str(k) for k in p if k not in _CREATE_FIELDS)
            if extra:
                why.append(f"unknown key(s) {_quote(extra)}")
            geo = p.get("geometry")
            if geo is not None and not isinstance(geo, dict):
                why.append("geometry is not an object")
            elif geo:
                if not (isinstance(geo.get("el"), str) and geo["el"] in _SHAPE_ELS):
                    why.append(f"geometry.el {_quote(geo.get('el'))}")
                if "viewBox" in geo and geo["viewBox"] != "0 0 100 100":
                    why.append(f"viewBox {_quote(geo['viewBox'])}")
                pts = geo.get("points")
                if pts is not None and not (isinstance(pts, str) and _POINTS_RE.match(pts)):
                    why.append(f"points {_quote(pts)}")
                attrs = geo.get("attrs")
                if attrs is not None and not isinstance(attrs, dict):
                    why.append("attrs is not an object")
                elif attrs:
                    for k, v in attrs.items():
                        if k not in _SHAPE_ATTRS:
                            why.append(f"attrs key {_quote(k)}")
                        elif isinstance(v, bool) or not _ATTR_VALUE_RE.match(_str(v)):
                            why.append(f"attrs value {_quote(v)} for {_quote(k)}")
                extra_geo = sorted(str(k) for k in geo if k not in {"viewBox", "el", "points", "attrs"})
                if extra_geo:
                    why.append(f"unknown geometry key(s) {_quote(extra_geo)}")
            if why:
                sys.stderr.write(
                    f"wtreconcile: {_patch_label(i, n, p)} has geometry the Overlay cannot "
                    f"emit: {'; '.join(why)} - do not copy it into source; ask before "
                    f"reconciling\n")


# Every property the Overlay can record: its panel controls, the per-side forms of
# margin/padding/border, the resize and move gestures, and the shape set.
_OVERLAY_PROPS = {
    "font-family", "font-size", "font-weight", "line-height", "letter-spacing",
    "text-align", "color", "background-color", "width", "height", "max-width",
    "min-height", "margin", "padding", "border", "border-radius", "box-shadow",
    "transform", "nudge", "fill", "stroke", "stroke-width", "rx", "position",
    "left", "top",
} | {f"{base}-{side}" for base in ("margin", "padding", "border")
     for side in ("top", "right", "bottom", "left")}
_BAD_CHARS = set("{};<@")
_BAD_SUBSTRINGS = ("url(", "expression(", "javascript:")


def _bad_text(v) -> bool:
    s = _str(v).lower()
    return any(c in s for c in _BAD_CHARS) or any(x in s for x in _BAD_SUBSTRINGS)


def _warn_unemittable_fields(pend: list) -> None:
    # SKILL.md has Claude write `selector`, every `changes`/`media` value and each media
    # condition into the real stylesheet. All of it comes from a file any page script
    # can forge, and the Overlay's CSS.supports gate and property list could never
    # record a `}`, a `url(` or a property it does not offer. SKILL.md says so in
    # prose; this makes the helper say it too. A flagged patch is held, not applied.
    for i, b in pend:
        for n, p in enumerate(b.get("patches") or []):
            why = []
            groups = [("changes", p.get("changes") or {})]
            groups += [(f"media {_quote(c)}", g) for c, g in (p.get("media") or {}).items()]
            for c in (p.get("media") or {}):
                if _bad_text(c):
                    why.append(f"media condition {_quote(c)}")
            for name, props in groups:
                for k, v in props.items():
                    if k not in _OVERLAY_PROPS:
                        why.append(f"{name} key {_quote(k)}")
                    if not isinstance(v, dict) and _bad_text(v):
                        why.append(f"{name} value {_quote(v)} for {_quote(k)}")
            sel = _str((p.get("fingerprint") or {}).get("selector"))
            if any(c in sel for c in _BAD_CHARS | {"\n", "\r"}):
                why.append(f"selector {_quote(sel)}")
            if why:
                sys.stderr.write(
                    f"wtreconcile: {_patch_label(i, n, p)} carries fields the Overlay "
                    f"cannot emit: {'; '.join(why)} - hold this patch, do not apply it; "
                    f"ask before reconciling\n")


def _warn_foreign_session_ids(pend: list) -> None:
    # sessionId is the one file-sourced value SKILL.md has Claude paste onto a command
    # line. One that the Overlay could not have generated is retired by index instead,
    # so the string never reaches a shell.
    for i, b in pend:
        sid = b.get("sessionId")
        if not (isinstance(sid, str) and _SESSION_RE.match(sid)):
            sys.stderr.write(
                f"wtreconcile: batch [{i}] has a sessionId ({_quote(sid)}) that did not "
                f"come from the Overlay - never put it on a command line; "
                f"mark it with `mark <file> --index {i}`\n")


def pending(args) -> None:
    doc = _load(args.file)
    pend = [(i, b) for i, b in enumerate(doc.get("batches") or [])
            if b.get("status") == "pending"]
    # Listed OLDEST FIRST, which is the order they must be applied in - not file order.
    # `applyBatch` replaces a session's pending batch IN PLACE rather than appending, so
    # a session that saves, is overtaken by a second session, then saves again leaves
    # the newest batch at the LOWEST index. A reader working down the listing would then
    # apply the newer value for a property and overwrite it with the older one. The
    # index is still printed so `[n]` keeps meaning "position in the file"; only the
    # order of presentation changes. Sorting here rather than only documenting it in
    # SKILL.md means the safe order is the one that costs no thought.
    pend.sort(key=lambda pair: (pair[1].get("savedAt") or "", pair[0]))
    _warn_impossible_media(pend)
    _warn_unemittable_geometry(pend)
    _warn_unemittable_fields(pend)
    _warn_foreign_session_ids(pend)

    if args.full:  # full patch JSON (fingerprints + changes) for deep work
        out = [
            {"index": i, "sessionId": b.get("sessionId"), "savedAt": b.get("savedAt"),
             "viewport": b.get("viewport"), "patchCount": len(b.get("patches") or []),
             "patches": b.get("patches") or []}
            for i, b in pend
        ]
        json.dump(out, sys.stdout, indent=2)
        print()
        return

    if not pend:
        print("no pending batches")
        return
    for i, b in pend:  # cheap orientation summary (read the file itself for full fingerprints)
        patches = b.get("patches") or []
        print(f"[{i}] session={_term(b.get('sessionId'))} "
              f"saved={_term(b.get('savedAt'), _STAMP_RE)} "
              f"viewport={_term(b.get('viewport'), _STAMP_RE)} patches={len(patches)}")
        for p in patches:
            # Flag create patches: they need a different reconcile path (insert
            # clean source, absolute placement sanctioned), and reading them as
            # edit patches sends Claude hunting for an element that isn't there.
            is_create = p.get("op") == "create"
            if is_create:
                lead = f"+ create {_flat(str(p.get('shape', 'shape')))} ->"
            else:
                lead = "-"
            line = f"    {lead} {_describe(p.get('fingerprint') or {})}  [{_changes_summary(p.get('changes') or {})}]"
            media = p.get("media") or {}
            if media:
                # `media?!` marks the impossible create+media combination (see
                # _warn_impossible_media) rather than rendering it as an ordinary
                # banded edit, which would read identically. SKILL.md quotes this
                # exact token - rename it there too.
                label = "media?!" if is_create else "media:"
                line += f"  {label} {_media_summary(media)}"
                # Only worth saying on a MIXED patch. With no `media` at all every
                # base property is un-banded, which is the pre-0016 status quo step 6
                # already handled - marking it there would be noise on every legacy
                # patch and would train the eye to skip the marker that matters.
                unbanded = _unbanded_summary(p.get("changes") or {}, media)
                if unbanded:
                    line += f"  base-only: {unbanded}"
            print(line)


def mark(args) -> None:
    """Flip a pending batch to reconciled. ALWAYS run this AFTER writing source.

    The order is a cross-component coupling, not a preference, and this is the end of
    the wire that can break it. The Overlay's restore() re-applies a batch that is still
    `pending`, and the live-reload guard uses the mark to know the batch is settled - so
    marking BEFORE the CSS is written opens a window where a reload finds a reconciled
    batch and freshly-unwritten source, or (worse) writes land after a restore has
    already re-applied the same patches and the nudge is doubled. CONTEXT.md records
    this as a named coupling ("SKILL.md steps 7 then 9") and overlay.js's restore()
    depends on it in two places; nothing enforces it in code, which is why it is stated
    at both ends rather than assumed.
    """
    doc = _load(args.file)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    if args.index is not None:
        if args.session is not None:
            _die("pass a sessionId or --index, not both")
        batches = doc.get("batches") or []
        if not 0 <= args.index < len(batches) or batches[args.index].get("status") != "pending":
            _die(f"no pending batch at index {args.index} - nothing marked")
        candidates = [batches[args.index]]
    else:
        candidates = [
            b for b in doc.get("batches") or []
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
        ids = ", ".join(_term(b.get("sessionId") or "?") for b in candidates)
        _die(f"{len(candidates)} pending batches ({ids}); pass a sessionId to mark one "
             f"at a time - reconcile each before marking it")

    # Reconcile reads the batch at step 1 and marks at step 9, and a Save in between
    # replaces the pending batch in place (same sessionId, new savedAt, more patches).
    # Marking by sessionId alone would retire patches that were never applied.
    if args.saved_at is not None:
        stale = [b for b in candidates if _str(b.get("savedAt")) != args.saved_at]
        if stale:
            _die(f"the pending batch was saved at {_term(stale[0].get('savedAt'), _STAMP_RE)}, "
                 f"not {_term(args.saved_at, _STAMP_RE)} - it changed after you read it, "
                 f"so re-run `pending` and reconcile the new patches; nothing marked")

    for b in candidates:
        b["status"] = "reconciled"
        b["reconciledAt"] = now

    _save(args.file, doc)
    print(f"marked {len(candidates)} batch(es) reconciled")


def status(args) -> None:
    doc = _load(args.file)
    batches = doc.get("batches") or []
    pend = [b for b in batches if b.get("status") == "pending"]
    recon = [b for b in batches if b.get("status") == "reconciled"]
    last_pending = max((b.get("savedAt") or "" for b in pend), default="")
    print(f"target:       {_term(doc.get('target'), _TARGET_RE, 120)}")
    print(f"pending:      {len(pend)}")
    print(f"reconciled:   {len(recon)}")
    print(f"last pending: {_term(last_pending, _STAMP_RE) if last_pending else '-'}")
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
                   help="sessionId to mark (if omitted, marks the single pending "
                        "batch; refuses when more than one is pending)")
    m.add_argument("--saved-at", dest="saved_at", metavar="TS", default=None,
                   help="refuse (marking nothing) unless the pending batch's savedAt "
                        "is exactly TS - the value `pending` printed when you read it")
    m.add_argument("--index", type=int, default=None, metavar="N",
                   help="mark the pending batch at file index N (the [n] `pending` "
                        "prints) instead of by sessionId")
    m.set_defaults(fn=mark)

    s = sub.add_parser("status", help="report pending vs reconciled counts")
    s.add_argument("file")
    s.set_defaults(fn=status)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
