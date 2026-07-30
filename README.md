# webtweak

**▶ Live demo &amp; site: https://stueydubs.github.io/webtweak/**

[![webtweak demo — edit by eye, Claude writes the CSS](https://raw.githubusercontent.com/stueydubs/webtweak/main/site/demo-poster.png)](https://stueydubs.github.io/webtweak/)

A local, open-source visual editor for hand-coded HTML/CSS pages. You drag, resize, and restyle an existing page by eye; webtweak captures what you changed as machine-readable patches; Claude reconciles those patches into the real source (and pushes only if you ask).

It is deliberately **half of a loop**. webtweak never rewrites your source - it only captures *intent*. The judgment-heavy work of locating elements and writing clean CSS is done by Claude on reconcile. That asymmetry is why a tool that would otherwise rival Pinegrow fits in one dependency-free script plus a browser overlay. See [`docs/adr/0001`](https://github.com/stueydubs/webtweak/blob/main/docs/adr/0001-capture-intent-not-rewrite-source.md).

**You need Claude for the second half.** Claude Code with the bundled skill is the smooth path (`webtweak --install-skill`), but any Claude conversation works - paste `reconcile/SKILL.md` and your edits file. And without an LLM at all, `page.webtweak.json` is still a plain readable list of exactly what you changed, which you can apply by hand.

**What v1 is for:** base layout and appearance work on hand-coded pages - resize, restyle, nudge, and drop in decorative shapes. It is *not* a responsive-design tool (you author at one viewport), it does not reorder your DOM, and it does not edit copy. Full list under [What v1 does not do](#what-v1-does-not-do).

## Install

**Requirements:** Node.js 18+ for the editor. **Python 3** as well if you want the reconcile helper. No npm packages required.

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
| `--root DIR` | Serve `DIR` as the web root instead of the page's own folder. Use it when the page lives in a subfolder and references root-absolute assets (`/css/site.css`) |
| `--port N` | Serve on port N (default 8723; `--port 0` picks any free port) |
| `--no-browser` | Don't auto-open the browser |
| `--install-skill` | Copy the reconcile skill into `~/.claude/skills/` and exit |
| `-v`, `--version` | Print the version |
| `-h`, `--help` | Show help |

In the browser:

- **Click** any element to select it (a breadcrumb shows where it sits).
- **Drag the interior** to nudge its position (snaps to a 4px grid).
- **Drag the right, bottom, or corner grip** (the gold handles on the selection box) to resize it.
- **Edit properties** in the right-hand panel - font, size, weight, line-height, letter-spacing, alignment, colours, width/height, margin, padding, border and corner radius.
- **Give an element a border.** Width, Style and Colour compose one `border` declaration. On an element with no border, touching any one of them fills in the other two so a border appears immediately - otherwise a colour on its own would render nothing at all. Style `none` removes a border; clearing a field abandons the change.
  - If the element already has a rule on **one side only** (a line under a heading), the controls edit *that side* and the group says which - so recolouring a divider leaves it a divider instead of boxing the element in. If several sides differ, the controls switch off with an explanation rather than replacing a deliberate design with a box.
- **Add a shadow from presets.** The Shadow field's ▾ offers a hairline, a card lift, a modal lift, a dramatic drop, an inset press, and `none` to take one off - so the property nobody remembers the syntax of is one you pick. Typing your own still works.
- **Pick a font from your own page.** The Font field's ▾ lists every font stack the page already uses, plus any family it declares as `@font-face`. Picking one writes the whole stack, so its fallbacks survive the edit; typing a stack by hand still works for a font you're introducing for the first time.
- **Draw a shape** from the shape button - square, rectangle, circle, ellipse, triangle, star, diamond, pentagon, hexagon. Drag one onto the page or click to place it. Each is one inline `<svg>` with editable fill, stroke and corner radius.
- **Cmd/Ctrl+Z** undoes your last change, of any kind.
- **Reset this element** discards all your edits to the selected element (also undoable).
- **Review before you save.** A "N elements changed" list sits bottom-left; open it to see every element you've touched and what changed on it, and click an entry to jump back to that element.
- **Save** when you're happy. **Cmd/Ctrl+S** saves, **Esc** deselects.

A reload mid-session is safe: webtweak restores the current session's pending edits, and warns you if you have unsaved changes.

### Watching the loop close

The bar carries a badge showing where your changes are: **N pending** once saved, **reconciled** once Claude has folded them into your source.

webtweak also watches the files it serves. When Claude rewrites your CSS, the page reloads itself and the badge flips — so you *see* your drag become real CSS instead of guessing and reloading by hand. If you have unsaved edits when the source changes, it will never reload over them; it offers you the reload instead.

## The loop

1. You make visual changes and hit **Save**.
2. webtweak writes a running-history edits file next to the page: `page.webtweak.json`. Each editing session is one *batch* of patches; re-saving overwrites that session's batch, and reconciled batches are kept as a permanent changelog.
3. You tell Claude *"I've adjusted page.html, reconcile it."*
4. Claude reads the pending batches, locates each element in your real source by its fingerprint, writes clean CSS in your conventions, and marks the batches reconciled. Reconcile stops at source - it never pushes, commits, or deploys unless you explicitly ask.

Your source is never touched until that reconcile step - running webtweak is consequence-free.

**Add these to your site's `.gitignore`** if you don't want the artefacts tracked (though the edits file makes a decent visual changelog if you do):

```gitignore
*.webtweak.json.tmp
*.webtweak.json.*.bak
```

## Installing the reconcile skill

The reconcile step is packaged as a [Claude Code](https://claude.ai/code) skill. Install it from wherever webtweak lives:

```bash
webtweak --install-skill
```

That works for a git clone, a global install, and npx alike. To copy it by hand from a clone instead:

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
- **Serves one directory as web root.** By default that is the page's own folder, so a page in a subfolder referencing site-root-absolute assets (`/assets/...`, `/css/site.css`) will 404 them. Pass `--root` at the real site root to fix it. Pages needing a build step (Tailwind compile, server-side partials) still won't render identically to production.

## Development

```bash
python3 -m pytest -m "not browser"      # unit + HTTP integration, no browser needed
```

The browser tests skip unless Playwright is installed, and a module skips as a *single* line - so check for the skip rather than assuming green:

```bash
pip install playwright && playwright install chromium
python3 -m pytest                        # everything, nothing skipped
```

Browser tests carry the `browser` marker and CI selects on it, never on a filename: a new browser module that CI does not know about would otherwise read green while never executing.

The unit tests drive `webtweak.js` itself (via `tests/_wtjs.py`), so they guard the code the package actually ships. CI runs the stdlib suite across Node 18/20/22/24 and the browser suite in a job where Playwright is always present.

No runtime dependencies. interact.js is vendored under `overlay/` for the drag/resize physics.

## Layout

- `webtweak.js` - the CLI/server: pure functions `injectOverlay` and `applyBatch` plus a thin HTTP handler. Node stdlib only. This is what ships.
- `overlay/` - the browser overlay (`overlay.js`, `overlay.css`, vendored `interact.min.js`)
- `fixtures/sample.html` - a sample editorial page for manual testing and the e2e
- `tests/` - unit, integration, and browser tests
- `reconcile/` - the Claude Code reconcile skill (`SKILL.md`) and the `wtreconcile.py` helper (Python 3)
- `CONTEXT.md`, `docs/` - the domain language, the PRD, the ADRs, and the issue breakdown

## License

MIT — see [LICENSE](LICENSE).

`overlay/interact.min.js` is [interact.js](https://interactjs.io) by Taye Adeyemi, also MIT.
