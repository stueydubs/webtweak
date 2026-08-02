# webtweak - AI instructions

A local, open-source visual editor for hand-coded HTML/CSS pages. You drag,
resize and restyle an existing page by eye; webtweak captures what changed as
machine-readable patches; Claude reconciles those patches into the real source.

Read [`CONTEXT.md`](./CONTEXT.md) before working here. It is the glossary and
the standing record of why the design is the shape it is, and its `_Avoid_`
lists exist because the wrong word has caused real confusion.

## House rules

### Never use em-dashes or en-dashes

Use a hyphen with spaces (`" - "`) everywhere a reader can see it. This is
gated: `tests/test_shipped_prose.py` fails on U+2014 EM DASH or U+2013 EN DASH
in `README.md`,
`package.json`, `LICENSE`, `overlay/VENDOR.md` and `reconcile/SKILL.md`, and it
also catches the Windows-1252 mojibake form (`â€"`), which is what actually
reaches a reader and what a grep for the real character misses. Live RSAs once
shipped with that mojibake. House style extends the rule to every file,
including this one.

### Zero runtime dependencies

`webtweak.js` is a single script over Node stdlib only. interact.js is
**vendored** under `overlay/` rather than fetched from a CDN, so the Overlay
works offline. Adding a runtime dependency is a decision to record in
`CONTEXT.md`, not a convenience. The reconcile helper
(`reconcile/scripts/wtreconcile.py`) is Python 3, so the full loop needs both
runtimes.

### Measure, don't reason, about rendered layout

Some Overlay layout is measured in JS and published to CSS because CSS cannot
ask the question. There are exactly three such channels (`--wt-bar-h`,
`--wt-panel-h`, `.wt-bar-wrapped`) and `CONTEXT.md` states the rule for adding a
fourth: if CSS *can* express it, it belongs in `overlay.css`. Only genuine "how
tall did that actually render" and "did that actually wrap" questions get a
channel, and each needs a named property or class plus a fallback for before the
first measurement.

### A passing test is evidence about the test first

Several tests in this repo were once passing for the wrong reason - sampling
grids that never touched the element under test, assertions that held whatever
the code did. When a test passes on the first run, check it fails when it
should. Prefer an explicit guard (`assert overlapped`) over a test that silently
degrades to vacuous when a fixture moves.

## Verifying a change

There are two suites, and `-m "not browser"` is **not** full coverage - it
excludes everything that drives the Overlay in a real page, which is most of
what webtweak does.

```bash
python3 -m pytest -m "not browser"    # unit + HTTP integration, no browser
.venv/bin/python -m pytest            # everything, nothing skipped
```

First-time browser setup:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/playwright install chromium
```

Browser modules skip as a **single line per module** when Playwright is absent,
so a suite missing them still reads green. Check the skip count, not the colour.

### Writing a browser test

Get the marker by importing the shared gate, never by hand:

```python
from _browser import sync_playwright, pytestmark   # noqa: F401
```

CI selects browser tests by **marker**, never by filename, because it once
selected by filename and three later modules were excluded from every job while
reading green. `tests/test_markers.py` enforces this and runs in the stdlib job,
which is exactly where a mis-marked module would otherwise sneak through.

## Releasing

The version must agree in five places: `package.json`, the newest `CHANGELOG.md`
heading, the git tag, the npm registry and the GitHub release.
`tests/test_shipped_prose.py` gates the first two against each other, checks
that every "Shipped in **X.Y.Z**" claim in the README exists in the CHANGELOG,
and asserts the `files` allowlist in `package.json` has not grown.

Run `npm publish --dry-run` before publishing, and verify the published artifact
by unpacking what the registry actually returns. A successful publish is not
proof the fix is in the tarball.

## Agent skills

### Issue tracker

Issues live in GitHub Issues on `stueydubs/webtweak`, accessed via the `gh` CLI.
Note that `docs/issues/` is a **historical** record from before this repo used
GitHub Issues, not the tracker. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical triage roles map 1:1 to their label strings (`needs-triage`,
`needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See
`docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root. Research findings
live in `docs/research/`. See `docs/agents/domain.md`.

### Work in flight

[Issue #1](https://github.com/stueydubs/webtweak/issues/1) is a `/wayfinder`
map toward webtweak 1.0. It deliberately revisits
[ADR-0001](./docs/adr/0001-capture-intent-not-rewrite-source.md), so a change in
that area should cite the ADR rather than quietly diverge from it.
