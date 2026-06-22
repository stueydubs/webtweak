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

## Relationships

- A **Target page** is edited via the **Overlay**, producing one or more **Patches**
- **Patches** are serialised into the **Edits file** (`<page-stem>.webtweak.json`)
- Claude reads the **Edits file** to **Reconcile** changes into the **Target page**'s real source

## Decisions captured

- **Element identity is a rich Fingerprint**, not a single selector and never an injected attribute. webtweak captures tag + id/classes + truncated text + `outerHTML` snippet + best-effort selector; Claude matches the bundle. Source is never mutated until Reconcile. Genuinely ambiguous cases (identical siblings) are flagged back to the user, not guessed.
- **v1 property scope is appearance + layout only.** Editable: typography (font-family, font-size, font-weight, line-height, letter-spacing, colour, text-align), box (width, height, margin, padding), background-colour, and a position nudge. Excluded from v1: borders, box-shadow, flex/grid alignment editors, hover/focus states, pseudo-elements, and editing text copy (copy changes are spoken to Claude, not done in the Overlay). No structural DOM reordering in v1.
- **A position nudge is captured as intent, not literal CSS.** webtweak stores a snapped (4px grid) pixel offset `(dx, dy)` from the element's natural position, previewed via `transform: translate(...)`. Claude reconciles small nudges into clean real-CSS (margin/padding/spacing in house conventions); large or flow-impossible drags are flagged as v2 reorders, never baked in as `position: absolute`/`transform` hacks. Trade-off accepted: intent-to-clean-CSS means a nudge may land at a tidy value (12px) rather than the exact drag distance (11px).
- **Stack: Python stdlib only, zero dependencies.** Single `webtweak` script over `http.server` (serve directory, inject Overlay, handle one POST to write edits.json). interact.js is vendored locally (not CDN) so the Overlay works offline. Matches existing Python CLI tooling; portable to Node later if ever needed.
- **Reconcile scopes to the single edited element by default, and flags systemic-looking changes.** Default output is CSS targeting only the element you touched (no surprise ripple to siblings sharing a class). When a change looks global (the only paragraph, or every heading changed alike), Claude pauses and asks "just this one or all `.section-title`s?" rather than guessing. Reconcile always writes real CSS rules into the stylesheet already governing the element - never inline styles.
- **v1 is single-viewport editing - changes are base CSS.** You author at one window width; webtweak stamps the session's viewport width into edits.json so Claude can warn when a desktop-width change would obviously break mobile and offer to scope it to a media query in that one case. Deliberate per-breakpoint authoring (auto-writing media queries) is v2. Honest limitation: v1 is for base-layout work, not responsive fine-tuning.
- **The edits file is a running history of Batches, never cleared.** Lives next to the Target page (`<page-stem>.webtweak.json`). Each Save overwrites the current `pending` Batch with a full snapshot of the session's Patches. Reconcile flips the Batch to `reconciled` (timestamped) and leaves it in place; Claude only ever applies `pending` Batches, so stale patches can't re-apply. To keep that history as a version-controlled changelog, commit the edits file **in the site's own repo** (the file lives beside the page being edited, not in the webtweak repo). The webtweak dev repo gitignores `*.webtweak.json` because there it only ever appears as a transient test artefact. Command: `webtweak <path-to-html>`; tool lives at `~/projects/webtweak/`, symlinked onto PATH.
- **Input is local source files**, not deployed URLs. webtweak opens the actual repo `.html` and serves its directory, so edits map directly to files Claude can push. (Caveat: pages needing a build step - Tailwind compile, partials - may not render identically to production; a non-issue for hand-coded editorial sites.)
