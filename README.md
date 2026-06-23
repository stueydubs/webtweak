# webtweak

A local, open-source visual editor for hand-coded HTML/CSS pages. You drag, resize, and restyle an existing page by eye; webtweak captures what you changed as machine-readable patches; Claude reconciles those patches into the real source (and pushes only if you ask).

It is deliberately **half of a loop**. webtweak never rewrites your source - it only captures *intent*. The judgment-heavy work of locating elements and writing clean CSS is done by Claude on reconcile. That asymmetry is why a tool that would otherwise rival Pinegrow fits in a single Python file plus a browser overlay. See [`docs/adr/0001`](docs/adr/0001-capture-intent-not-rewrite-source.md).

## Install

**Requirements:** Node.js 18+. No npm packages required.

```bash
npm install -g webtweak
```

Or run without installing:

```bash
npx webtweak page.html
```

**From source:**

```bash
git clone https://github.com/stueydubs/webtweak
cd webtweak
npm link
```

Then run `webtweak --help` to confirm it's working.

## Usage

```bash
webtweak path/to/page.html
```

This boots a local server, serves the page's own directory (so CSS, images, and fonts resolve as in production), injects the editing overlay, and opens your browser.

| Flag | Effect |
|---|---|
| `--port N` | Serve on port N (default 8723; `--port 0` picks any free port) |
| `--no-browser` | Don't auto-open the browser |

In the browser:

- **Click** any element to select it (a breadcrumb shows where it sits).
- **Drag the interior** to nudge its position (snaps to a 4px grid).
- **Drag the right, bottom, or corner grip** (the gold handles on the selection box) to resize it.
- **Edit properties** in the right-hand panel - font, size, weight, line-height, letter-spacing, alignment, colours, width/height, margin, padding.
- **Reset this element** undoes your edits to the selected element.
- **Save** when you're happy. **Cmd/Ctrl+S** saves, **Esc** deselects.

A reload mid-session is safe: webtweak restores the current session's pending edits, and warns you if you have unsaved changes.

## The loop

1. You make visual changes and hit **Save**.
2. webtweak writes a running-history edits file next to the page: `page.webtweak.json`. Each editing session is one *batch* of patches; re-saving overwrites that session's batch, and reconciled batches are kept as a permanent changelog.
3. You tell Claude *"I've adjusted page.html, reconcile it."*
4. Claude reads the pending batches, locates each element in your real source by its fingerprint, writes clean CSS in your conventions, and marks the batches reconciled. Reconcile stops at source - it never pushes, commits, or deploys unless you explicitly ask.

Your source is never touched until that reconcile step - running webtweak is consequence-free.

## Installing the reconcile skill

The reconcile step is packaged as a [Claude Code](https://claude.ai/code) skill. Copy it into your Claude skills directory:

```bash
mkdir -p ~/.claude/skills
cp -r reconcile ~/.claude/skills/webtweak-reconcile
```

Then from any Claude Code conversation, in your site's project directory:

```
/webtweak-reconcile
```

Claude reads the pending patches, proposes CSS changes, writes them to source, and marks the batch done. If you don't use Claude Code, `reconcile/SKILL.md` documents the full process as plain instructions you can give any Claude conversation.

## What v1 does not do

- **No structural reordering.** Moving an element above another (rewriting the DOM order in source) is deferred to v2. v1 is resize, restyle, and nudge.
- **No copy editing.** Changing the actual words is spoken to Claude, not done in the overlay.
- **Single viewport.** Changes are authored as base CSS; the session's viewport width is recorded so Claude can warn about mobile breakage, but deliberate per-breakpoint authoring is v2.
- **Limited property set.** Borders, shadows, flex/grid alignment editors, and hover states are out of the v1 panel.
- **Serves the page's own directory as web root.** A page in a subfolder that references site-root-absolute assets (`/assets/...`, `/css/site.css`) will 404 those and render with fallback styling. Open such a page from the repo root (or pass a path relative to it) so the real site root is `/`.

## Development

```bash
python3 -m pytest tests/         # unit + HTTP integration tests (stdlib only)
```

The browser end-to-end test (`tests/test_e2e_browser.py`) skips unless Playwright is installed:

```bash
pip install playwright && playwright install chromium
python3 -m pytest tests/test_e2e_browser.py
```

Python stdlib only, no runtime dependencies. interact.js is vendored under `overlay/` for the drag/resize physics.

## Layout

- `webtweak` - the CLI/server (pure functions `inject_overlay` and `apply_batch` plus a thin HTTP handler)
- `overlay/` - the browser overlay (`overlay.js`, `overlay.css`, vendored `interact.min.js`)
- `fixtures/sample.html` - a sample editorial page for manual testing and the e2e
- `tests/` - unit, integration, and browser tests
- `reconcile/` - the Claude Code reconcile skill (`SKILL.md`) and the `wtreconcile.py` helper
- `CONTEXT.md`, `docs/` - the domain language, the PRD, the ADR, and the issue breakdown

## License

MIT — see [LICENSE](LICENSE).

`overlay/interact.min.js` is [interact.js](https://interactjs.io) by Taye Adeyemi, also MIT.
