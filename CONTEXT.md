# webtweak

A local, open-source visual editor for hand-coded HTML/CSS pages. You manipulate an existing page visually (resize, restyle, nudge, change fonts); webtweak captures what changed as machine-readable patches; Claude reconciles those patches into the real source files and pushes. Built as a free alternative to paid visual editors like Pinegrow, for hand-coded editorial sites, exploiting the fact that a human-plus-Claude loop means the editor only has to *capture intent*, not flawlessly rewrite source.

## Language

**Target page**:
The local source `.html` file webtweak is opened against. webtweak serves its directory so CSS/images/fonts resolve as in the real build.
_Avoid_: live site, URL, deploy

**Overlay**:
The editing UI injected on top of the Target page in the browser - element picker, drag/resize handles, properties panel.
_Avoid_: editor (too vague), canvas

**Patch**:
One captured change to one element - the element's identity plus the property/value that changed.

**Fingerprint**:
The bundle of signals a Patch carries to identify its element without mutating source - tag, id, classes, truncated text and own-text, a clean opening tag (`openTag`, inline `style` stripped), and a positional CSS `selector` used only as a weak tiebreaker. Claude locates the element in real source by matching the whole bundle, the way a human would.

**Edits file**:
The file webtweak writes containing all Patches, the hand-off artefact Claude reads. On disk it is named `<page-stem>.webtweak.json`, next to the Target page. (There is no file literally called `edits.json`; "edits file" is the abstract term.)

**Batch**:
One editing session's worth of Patches inside the edits file, stamped with viewport + timestamp and a status of `pending` or `reconciled`. Claude only applies `pending` Batches; reconciled ones stay as history.

**Reconcile**:
Claude's half of the loop - reading the edits file and applying the Patches cleanly into the real source files (proper CSS, house conventions). Reconcile stops at source; it does not push.
_Avoid_: merge, sync

**Border**:
A CSS `border` on an ordinary page element - composed in the panel from Width, Style and Colour, and emitted as one declaration (or a per-side `border-bottom` when the element carries a rule on one side only).
_Avoid_: using it for a shape's outline, which is a Stroke

**Stroke**:
A shape's outline - the SVG `stroke`/`stroke-width` on a created shape's `<svg>`. Distinct from Border by design, not by accident: ADR-0002 chose SVG precisely so a real outline renders on every shape kind, and a CSS border on the wrapper would draw a rectangle around a triangle. The panel's shape controls are therefore labelled Stroke and Stroke width, and the Border group hides for shapes. A shape's **Radius** keeps that name, because `rx` and `border-radius` are the same concept in the same units.
_Avoid_: border, outline

## Relationships

- A **Target page** is edited via the **Overlay**, producing one or more **Patches**
- **Patches** are serialised into the **Edits file** (`<page-stem>.webtweak.json`)
- Claude reads the **Edits file** to **Reconcile** changes into the **Target page**'s real source

## Decisions captured

- **Element identity is a rich Fingerprint**, not a single selector and never an injected attribute. webtweak captures tag + id/classes + truncated text + `outerHTML` snippet + best-effort selector; Claude matches the bundle. Source is never mutated until Reconcile. Genuinely ambiguous cases (identical siblings) are flagged back to the user, not guessed.
- **Property scope is appearance + layout only.** Editable: typography (font-family, font-size, font-weight, line-height, letter-spacing, colour, text-align), box (width, height, margin, padding), background-colour, **border, corner radius and box-shadow** (added in 0.4.0), and a position nudge. Font is picked from a list of the Target page's own font stacks; shadow from a list of presets; both lists still accept free text. Still excluded: flex/grid alignment editors, hover/focus states, pseudo-elements, per-corner radii, per-side border controls (an element whose sides differ is declined, not editable - see ADR-0003), and editing text copy (copy changes are spoken to Claude, not done in the Overlay). No structural DOM reordering.
- **Border is composed from three controls and seeded so every control is visible.** Width, Style and Colour write one `border` declaration, and touching any of them on a border-less element seeds the other two - because a colour alone and a width alone both render nothing while the initial style is `none`, and recording an invisible change is the phantom-patch failure this codebase keeps re-learning. An element bordered on exactly one side has that side edited instead (`border-bottom`), since composing four sides onto a heading's rule would turn a divider into a box; an element whose sides differ is declined outright. See [ADR-0003](./docs/adr/0003-compose-shorthands-from-discrete-controls.md).
- **A position nudge is captured as intent, not literal CSS.** webtweak stores a snapped (4px grid) pixel offset `(dx, dy)` from the element's natural position, previewed via `transform: translate(...)`. Claude reconciles small nudges into clean real-CSS (margin/padding/spacing in house conventions); large or flow-impossible drags are flagged as v2 reorders, never baked in as `position: absolute`/`transform` hacks. Trade-off accepted: intent-to-clean-CSS means a nudge may land at a tidy value (12px) rather than the exact drag distance (11px).
- **Stack: Node stdlib only, zero dependencies.** Single `webtweak.js` script over `node:http` (serve directory, inject Overlay, handle one POST to write the edits file). interact.js is vendored locally (not CDN) so the Overlay works offline. Originally a single Python file; rewritten in Node at `cfe23ff` so the tool could ship on npm as `npx webtweak`, since its audience already has Node. The Python reference implementation was kept in parallel for a while and deleted in 0.2.0 once the unit tests were repointed at the shipped Node functions - a second implementation the tests asserted against, but users never ran, made the suite read as safer than it was. The reconcile *helper* (`reconcile/scripts/wtreconcile.py`) is still Python 3, so the full loop needs both runtimes.
- **Reconcile scopes to the single edited element by default, and flags systemic-looking changes.** Default output is CSS targeting only the element you touched (no surprise ripple to siblings sharing a class). When a change looks global (the only paragraph, or every heading changed alike), Claude pauses and asks "just this one or all `.section-title`s?" rather than guessing. Reconcile always writes real CSS rules into the stylesheet already governing the element - never inline styles.
- **v1 is single-viewport editing - changes are base CSS.** You author at one window width; webtweak stamps the session's viewport width into edits.json so Claude can warn when a desktop-width change would obviously break mobile and offer to scope it to a media query in that one case. Deliberate per-breakpoint authoring (auto-writing media queries) is v2. Honest limitation: v1 is for base-layout work, not responsive fine-tuning.
- **The edits file is a running history of Batches, never cleared.** Lives next to the Target page (`<page-stem>.webtweak.json`). Each Save overwrites the current `pending` Batch with a full snapshot of the session's Patches. Reconcile flips the Batch to `reconciled` (timestamped) and leaves it in place; Claude only ever applies `pending` Batches, so stale patches can't re-apply. To keep that history as a version-controlled changelog, commit the edits file **in the site's own repo** (the file lives beside the page being edited, not in the webtweak repo). The webtweak dev repo gitignores `*.webtweak.json` because there it only ever appears as a transient test artefact. Command: `webtweak <path-to-html>`; published to npm, and the dev copy lives at `~/projects/webtweak/`.
- **The server watches the served tree and pushes reloads, so the loop is visible.** Reconcile happens in another window; before this, the user saved and had no signal until they reloaded by hand. webtweak watches its served directory and sends events over SSE (`GET /__webtweak__/events`); a clean page reloads itself, so a reconcile lands in front of the user, and a **reconcile badge** reflects the edits file's own view (`N pending` until Claude flips the batch to `reconciled`). **Three rules make it safe**, and the third is the subtle one:
  1. A reload **never** runs over unsaved edits. Guarded on `dirty`, not on "has edits" - after a Save the batch is on disk and `restore()` re-applies it, and reloading after a save is exactly the case that matters.
  2. webtweak's own temp/backup artefacts are excluded, or every Save would bounce the page being edited.
  3. **A reload never runs while this session's Batch is still `pending`.** Reconcile writes source *first* and marks the Batch *second* (SKILL.md steps 7 then 8), so there is a window where the CSS is already rewritten but the Batch still says pending - and `restore()` would re-apply it on top, doubling a nudge and re-emitting the same Patches on the next Save. This is a **cross-component ordering coupling**: it depends on reconcile's step order, and if reconcile ever marked *before* writing, the Overlay would double-apply silently. The Edits file is therefore watched as its own `edits-change` event (a mark touches only that file, so without it the badge could never reach `reconciled`), with webtweak's own save recognised by comparing the exact bytes it wrote.

  Watching is per-directory rather than `fs.watch(recursive)`, which only reached Linux in Node 20 while the package supports 18; if watching fails the tool degrades to no live reload, never to a crash.
- **Input is local source files**, not deployed URLs. webtweak opens the actual repo `.html` and serves one directory as the web root - the page's own folder by default, or `--root DIR` when the page sits in a subfolder and references root-absolute assets (`/css/site.css`). The Edits file always lands beside the *page*, not in the web root. (Caveat: pages needing a build step - Tailwind compile, partials - may not render identically to production; a non-issue for hand-coded editorial sites.)
- **Shape creation is webtweak's first element-creation feature, via a `create` Patch op.** You can draw decorative shapes (square, rectangle, circle, ellipse, triangle, star, diamond, pentagon, hexagon) onto the page; each is one inline `<svg>` (uniform renderer, so a real stroke renders on every shape and `fill`/`stroke`/`stroke-width` cascade from the wrapper to the child). A shape drops at the click point as a `position: absolute` element - the sanctioned exception to the no-`position:absolute` rule, which governs flow content + nudges, not a genuine decorative absolute layer. A shape reuses the whole existing Patch/select/resize/undo/restore machinery, marked `e.shape`, and on Save emits `{ op: "create", shape, geometry, anchor, fingerprint, changes }` (self-contained; server stores it verbatim). Reconcile learns to *insert* clean source for it, stripping the throwaway `wt-shape-<rand>` id. See [ADR-0002](./docs/adr/0002-shape-creation.md). This narrows but does not close ADR-0001: webtweak still never rewrites existing source - it only appends a self-contained new element for Claude to reconcile.
