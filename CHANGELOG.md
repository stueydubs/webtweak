# Changelog

All notable changes to webtweak are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Existing elements can have a border.** A decorative shape could have one and
  the card beside it could not, which read as a bug rather than a scope boundary.
  A Border group joins the panel with Width, Style, Colour and corner Radius,
  hidden for shapes the way typography and colour already are.

  The three border controls compose **one** `border` declaration, and touching any
  one of them on a border-less element seeds the other two so a border renders
  immediately. Without that, two of the three controls would do nothing visible on
  first use - a colour alone and a width alone both render nothing while the style
  is `none` - and the overlay would still record the value, putting a Patch for an
  invisible change into your source. The seeded colour is your element's own text
  colour, so the swatch was already showing it. Style `none` removes a border and
  records as `border: none`; clearing any field abandons the whole change. See
  [ADR-0003](./docs/adr/0003-compose-shorthands-from-discrete-controls.md).
- **A Shadow field, with presets.** `box-shadow` is the one property here that
  resists discrete controls: building it from parts would need four lengths, a colour
  and an inset flag, and a shadow's colour is almost always translucent while the
  panel's swatch is opaque hex. So it is a text field backed by the same suggestion
  list the Font control uses - a hairline, a card lift, a modal lift, a dramatic drop,
  an inset press, and `none` to remove one. Typing a custom shadow still works.
- **A rule on one side stays a rule.** Bottom borders under headings are everywhere
  on the editorial pages webtweak is for, and composing a four-sided border onto one
  would turn a divider into a box. When exactly one side carries a visible border the
  controls edit *that side*, the group legend names it, and the Patch says
  `border-bottom` - which reconcile is now told never to normalise back to all sides,
  because the side is the intent. When several sides differ the controls switch off
  with an explanation, the same way width and height already switch off on an inline
  element: the overlay declines rather than quietly wrecking a deliberate design.
- **The Font control offers the page's own fonts.** It was the one field that
  demanded you already knew an exact string: to set a heading in the site's
  display face you had to type `Fraunces, Georgia, serif` from memory, fallbacks
  and all, and a typo silently recorded nothing at all. The field now carries a ▾
  listing every distinct font stack in use on the page plus any family it declares
  as `@font-face`, each row previewed in its own face. Picking one writes the whole
  stack, so the fallbacks the page's author intended survive by construction rather
  than by your care. It stays a text input - typing an arbitrary stack still works,
  so a font you are introducing for the first time is not blocked by a list that
  cannot know about it.

  The list is built from computed style, which is the only origin-proof source: a
  page whose display face comes from a CDN-hosted webfont yields nothing readable
  from its stylesheets (`SecurityError`), and that is the common case, not the edge
  case. `@font-face` families are gathered from readable sheets as a supplement, so
  a self-hosted face you have set up but not yet applied anywhere is still one
  click away - and an unreadable sheet degrades the list instead of throwing.

### Fixed
- **A typo no longer deletes the edit you had just made.** An invalid value resolves
  to the element's *current* computed value, which is indistinguishable from setting
  the field back to its original - so mistyping over a margin (or, now, a shadow) you
  had just set silently discarded it instead of being ignored. Values are rejected
  before that comparison, so a typo leaves your work alone and says so.
- **The right-hand shape palette items are clickable again while something is
  selected.** The palette drops out of the top bar into the properties panel's
  column, and the panel painted over it, so three of the nine shapes could not be
  picked at all except with nothing selected.

### Changed
- A shape's controls read **Stroke** and **Stroke width** rather than Border and
  Border width, now that "Border" means a CSS border elsewhere in the same panel.
  Labels only - the properties were always the SVG ones, so nothing changes in a
  Patch or in reconcile. The shape's Radius keeps its name: `rx` and
  `border-radius` are the same concept in the same units.

## [0.3.0] - 2026-07-30

### Security
- **The breadcrumb no longer executes markup from the page you are editing.** It
  was built with `innerHTML` from the element's own tag, id and class names, so
  opening a page from a repo you did not write and clicking an element ran its id
  as HTML - in the overlay's origin, which can POST patches that Claude later
  reconciles into your real source. Now built with `textContent`. The session
  change list added in this release was already safe; the breadcrumb beside it
  never had been.
- **The file watcher can no longer be walked out of the served directory.** Its
  initial scan correctly refuses to follow symlinks, but an `fs.watch` event
  carries only a name, so the child was `stat`ed - and a stat follows links. A
  symlink created while webtweak was running therefore had it watching, and
  reporting filenames from, directories outside the web root.

### Added
- **The loop closes in the browser.** webtweak now watches the files it serves
  and pushes an event when the source under the page changes, so a reconcile
  lands visibly: the page reloads itself and you watch your drag become real
  CSS. Previously the hand-off was blind - you saved, switched to Claude, and
  had no signal at all until you reloaded by hand.
  - A **reconcile badge** in the bar reads `N pending` after a save and
    `reconciled` once Claude has folded the batch into source.
  - A live reload **never runs over unsaved edits**. With unsaved work the badge
    offers the reload instead of taking it.
  - webtweak's own temp and backup files are excluded from the watch, so saving
    cannot bounce the page you are still editing. The edits file itself *is*
    watched, as its own event - reconcile marks a batch by touching only that
    file, so without it the badge could never reach `reconciled`.
- **`--root DIR`** serves an explicit web root instead of the page's own folder,
  so a page in a subfolder can resolve root-absolute assets (`/css/site.css`).
  Previously unsupported, which ruled out most real sites. The edits file still
  lands beside the page, not in the root.
- **Session change list** - a collapsible "N elements changed" panel listing
  every element you have touched and what changed on it; click an entry to
  select and scroll to it. `edited` held the whole session but the properties
  panel only ever showed one element, so reviewing meant saving and opening the
  JSON.

### Changed
- The save confirmation names the edits file it wrote, which teaches the
  hand-off for free.
- The panel note no longer reads as though saving invokes Claude. Save writes a
  file; reconcile is a separate step you ask for.
- `--help` documents `--root`; the opened URL is percent-encoded, so a folder
  named `my blog` or `a#b` no longer produces a link that 404s.

### Fixed
All of the below are in the live-reload machinery added above, found by review
before release rather than in use.
- **A reload can never discard your session.** Every safety check now fails
  closed. Deleting or reverting the edits file - `git checkout .` in your site
  repo, which is an ordinary thing to do since the file is meant to be committed
  there - used to read as "already reconciled" and trigger a reload that threw
  the session away. It now says `edits file gone` and leaves your edits on screen
  so you can re-save them.
- A reload only happens on the *transition* to reconciled, and only for **your**
  session's batch. Another session's batch being marked no longer yanks the page
  out from under you mid-review.
- A save no longer silently dismisses a `source changed - reload` warning. The
  source is still stale and nothing else will raise it again, so the decision is
  re-run instead of dropped.
- The badge cannot get stuck. It used to latch on `reconciling...` for the rest
  of the session whenever reconcile deliberately left a batch pending (which it
  is instructed to do when a patch needs your answer), with no way out.
- The green `reconciled` badge clears the moment you start editing again, instead
  of reading as "already in source" over unsaved work.
- No reload during an in-flight save, and the unsaved-changes prompt stays honest
  for that window - previously both treated the page as saved before the write
  had landed.
- A page in a very deep directory, or a very large tree, now says that live
  reload is partly off rather than silently never firing.
- The change list keeps its scroll position: rows are rebuilt only when they
  actually change, not on every click and keystroke.

## [0.2.0] - 2026-07-29

### Security
- The save endpoint now rejects cross-origin writes. Any page open in the same
  browser could previously POST to webtweak's (fixed, guessable) port and write
  a batch into the edits file - which Claude then reads as instructions during
  reconcile, so an unauthenticated write reached real source. Saves now require a
  same-origin `Origin` (or none, for a non-browser client) and
  `Content-Type: application/json`; `text/plain` was a CORS *simple* request no
  preflight could stop.
- A forged `Host` header is now rejected, closing a DNS-rebinding path that made
  the served directory readable by an attacker-controlled page.
- Symlinks can no longer escape the served directory. The traversal guard resolved
  `..` correctly but did not resolve symlinks, so a link inside your site folder
  served any file on disk.

### Added
- **Shape creation** - draw decorative shapes (square, rectangle, circle,
  ellipse, triangle, star, diamond, pentagon, hexagon) onto the page from a new
  "Shape" palette in the top bar. Place a shape by clicking the palette then
  clicking the page, **or by dragging the shape straight from the palette onto the
  page** and releasing where you want it. webtweak's first element-creation
  feature. Each shape is one inline `<svg>`, so a real stroke renders on every kind
  and fill/border colour cascade uniformly.
- **Shape panel group** - Fill, Border (stroke) colour, Border width, and corner
  Radius (rect/square only), on top of the existing Box width/height controls.
- Shapes drag anywhere on their body to reposition (true move), resize by grabbing
  the corner/edge grips, undo (Cmd/Ctrl+Z removes a just-created shape), and restore
  after reload like any other edit.

### Changed
- The selection resize grips are now functional drag handles you grab directly,
  rather than visual hints. Previously the resize zone sat just inside the element
  edge while the grips were drawn on the edge, so aiming at a grip often missed;
  resizing (shapes especially) now works wherever the grip is shown.
- New patch op `op: "create"` carrying the shape kind, self-describing geometry,
  an insertion anchor, and a full style snapshot; the reconcile skill gained an
  insert path that writes clean source for it. See ADR-0002.

### Fixed
- A shape's controls now always record (a shape has no authored baseline), so a
  1px border width or a `#000000` fill/stroke is captured rather than mistaken for
  a revert against the SVG default and silently dropped from the patch.
- Restoring saved shapes after a reload no longer marks the page as having unsaved
  changes (no spurious "leave site?" prompt).
- Grip-resize now resolves coordinates correctly under a `transform: scale()`
  ancestor (e.g. A4/print-preview layouts).
- Picking a shape to place now clears any current selection first, so its grips
  can't swallow the placement click; Deselect/Esc cancels an in-progress placement.
- **Clearing a field now reverts that change** instead of doing nothing. Typing a
  value and then emptying the box left the abandoned value recorded, so it shipped
  to Claude and got written into your real source.
- **The selection no longer jumps after a drag.** Every nudge or resize was
  followed by a browser click that re-selected whichever child sat under the
  cursor, so the grips silently moved to an element you never chose and the next
  resize targeted the wrong thing.
- **Reset is undoable.** It recorded no undo step, so on a shape it was an
  unrecoverable delete, and on any element it discarded every edit with no way back.
- Undoing past a Reset no longer resurrects the deleted element as a phantom
  patch carrying a fingerprint computed on a detached node.
- A directory URL now serves its `index.html` instead of 404ing, so root-relative
  nav links (`href="/"`) work. Directory listings stay off.
- The overlay is only injected into the page you opened. Following a nav link
  previously gave you a fully functional editor pointed at the wrong page, whose
  saves landed in the original page's edits file with mismatched fingerprints.
- The overlay UI mounts on `<html>` rather than `<body>`, so a page with
  `body { transform: scale(...) }` (A4/print layouts) no longer renders the whole
  editor scaled and mis-anchored.
- A page's own `wt-`prefixed classes are no longer stripped from the fingerprint;
  only webtweak's own `wt-shape` class is.
- If a corrupt edits file cannot be backed up, the save now fails loudly instead
  of overwriting the only copy while logging that a backup was taken. Backups are
  capped at the newest 3.
- `--version` works; `--port` validates its range instead of crashing with a raw
  Node stack trace; `--port=N` is accepted; a directory argument says so; passing
  two pages is an error rather than silently using the last.
- The reconcile helper writes UTF-8 rather than `\u` escapes, matching the server,
  so marking a batch no longer rewrites every non-ASCII character in your repo.

### Changed
- `--help` now documents every flag, the loop, and the Python 3 requirement.
- New `--install-skill` flag copies the bundled reconcile skill into
  `~/.claude/skills/`, which works identically for a clone, a global install and
  npx. Previously only a git clone had a documented path.
- Static files stream rather than being read whole, and `Range` requests are
  supported - a large asset no longer blocks the single-threaded server, and
  `<video>` plays in Safari and on iOS.
- Added MIME types for `.webmanifest`, `.map`, `.mp3`, `.ogg`, `.wasm`, `.csv`
  and `.jsonld`, which previously loaded as `application/octet-stream`.
- Startup reports any batches left unreconciled from a previous session.
- `reconcile/scripts/wtreconcile.py` is executable, as the skill's own
  instructions assume. It previously failed with `Permission denied` for everyone.
- The reconcile skill now covers the zero-match case, fingerprint truncation, and
  a verification pass; it requires every patch to be accounted for before a batch
  is marked, so a skipped patch can no longer be silently retired. Its nudge
  guidance is corrected: small offsets are intent, never drag jitter, and
  `position: relative` is an acceptable clean form.

### Removed
- The parallel Python implementation (`webtweak.py`). The unit tests asserted
  against it while users ran `webtweak.js`, so two deliberately broken invariants
  in the shipped code - including "a reconciled batch is never modified" - left the
  suite fully green. The tests now drive `webtweak.js` itself, and CI runs them
  across Node 18/20/22/24 plus a dedicated browser job where Playwright is always
  installed (its 31 e2e tests previously collapsed into one silent skip line).

## [0.1.1] - 2026-06-24

### Fixed
- Clicking empty space (the page body or root) now deselects the current
  element instead of leaving it stuck selected.
- Drag and resize are more robust on A4, scaled, and SVG pages.
- Removed a stray `./` prefix from the bin path so the npm package resolves
  correctly when installed globally or run via npx.

## [0.1.0] - 2026-06-23

### Added
- Initial release. A local visual editor for hand-coded HTML/CSS pages: drag,
  resize, and restyle an existing page by eye while webtweak captures the
  changes as machine-readable patches.
- Node.js server (`webtweak <page.html>`) that serves the page's own directory
  and injects the editing overlay.
- `--port` and `--no-browser` flags.
- Reconcile skill (`reconcile/`) for folding captured patches into source CSS.
- Published to npm; installable globally or runnable via `npx webtweak`.

[Unreleased]: https://github.com/stueydubs/webtweak/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/stueydubs/webtweak/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/stueydubs/webtweak/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/stueydubs/webtweak/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/stueydubs/webtweak/releases/tag/v0.1.0
