---
name: webtweak-reconcile
description: Reconcile visual edits captured by the webtweak tool into a site's real source. Reads a <page>.webtweak.json edits file, locates each patched element by its fingerprint, writes clean CSS in the site's house conventions (single-element scope by default), translates nudge intent into clean margin/padding, and marks batches reconciled. Use when the user has finished a webtweak session, says "reconcile my webtweak edits", "apply the webtweak changes", mentions a *.webtweak.json file, or wants webtweak edits folded into source and optionally pushed.
---

# webtweak reconcile

The second half of the webtweak loop. The webtweak tool captures visual edits as *intent* and never touches source; this skill turns that intent into clean source. Reconcile is judgment work - when a match or a scope decision is genuinely ambiguous, ask rather than guess. That is the whole reason this half is a skill and not code.

## Input

A `<page>.webtweak.json` file sitting next to the edited page:

```
{ target, batches: [ { sessionId, savedAt, viewport, status, patches: [ { fingerprint, changes: { ...cssProps, nudge? } } ] } ] }
```

Only `status: "pending"` batches are reconciled. `reconciled` batches are history - never re-apply them.

Two patch shapes share the array. An **edit patch** (`{ fingerprint, changes }`, no `op`) restyles an element that already exists in source - the original and most common case. A **create patch** (`{ op: "create", ... }`) *inserts* a new shape element - webtweak's only element-creation feature. Branch on `op`: treat anything without `op` (or with `op: "edit"`) as an edit patch; `op: "create"` is handled in **"The `create` op"** below.

- `fingerprint`: `{ tag, id, classes, text, ownText, selector, siblingIndex, openTag }`. `ownText` is the element's own direct text (excluding descendants') - prefer it for matching leaf/text elements; `text` includes descendant text - use it to disambiguate containers. `openTag` is the opening tag with any injected inline `style` stripped, so it matches clean source. `selector` is a positional `nth-of-type` path - a weak tiebreaker only. `siblingIndex` is the element's 0-based position among siblings sharing its tag+classes - use it to name *which* one when several are otherwise identical.
- `changes`: CSS property→value (kebab-case). A position nudge lives *inside* `changes` as `changes.nudge = { dx, dy }` (a 4px-snapped pixel offset), not a separate patch field.
- `viewport`: the authoring window width in px (an integer).
- **Captured values can be computed, not authored.** Several controls read `getComputedStyle`, so the value may be resolved rather than what the author wrote - do **not** treat these as ground truth; cross-check against source before writing (see step 5): `line-height`/`letter-spacing` may arrive as absolute px instead of a unitless ratio or em; `margin`/`padding` as resolved 4-value px that has lost `auto` (centering) or `%`; `width`/`height` as fixed px over an authored `%`/`auto`/`max-width`; colours may be alpha-stripped (a transparent element reads as opaque `#000000`).

## Workflow

1. **Find the work.** Locate the edits file (a given path, or `*.webtweak.json` beside the page). Run `scripts/wtreconcile.py pending <file>` for a summary of pending batches (add `--full`, or read the file directly, for complete fingerprints). If none, say so and stop.
2. **Read the house style.** Open the stylesheet(s) governing the page. Note indentation, selector conventions, units, custom properties, and spelling - match them.
3. **Locate each element.** Resolve the fingerprint the way a human would, in priority order: `id` (before accepting, confirm the located element's `tag` matches `fingerprint.tag` - guards a stale id moved to a different element) → `classes` + `ownText`/`text` (+ `tag`) → `openTag`. Use `selector` only as a last-resort tiebreaker or confirmation, never as a primary locator - it is a positional `nth-of-type` path captured on the injected DOM, so it is the least trustworthy signal and can be stale. If two candidates still match equally well (identical siblings), use `siblingIndex` to name which one; if it is still genuinely ambiguous, STOP and ask - never guess.
4. **Decide scope** (per patch). Default: change only the element that was edited. If it is targeted by a shared class AND the change looks systemic (every sibling changed alike, or it is the sole instance of that class), ask "just this one, or all `.class`?". If single-element scope needs a selector hook the source lacks, prefer the captured `selector`; only add a class to the HTML after asking.
5. **Translate the changes.**
   - Plain CSS props → write as-is into the governing rule (or a targeted rule for single-element scope). One gotcha: a multi-word `font-family` may arrive unquoted (e.g. `font-family: Helvetica Neue`) - quote the family name on write (`"Helvetica Neue"`) so the CSS is valid.
   - **Suspect computed-not-authored values** (per the Input caveat) - check each against the source declaration before writing, don't bake the resolved value:
     - `line-height` as px (e.g. `33.6px`): if source authored a unitless ratio or em, keep that form - recompute the ratio from the new px ÷ the element's font-size, or ask for the ratio. Same for em `letter-spacing`.
     - `margin`/`padding` as 4-value px where source had `auto` (centering) or `%`: preserve the `auto`/`%`; only change the side(s) the user actually moved, not the whole shorthand.
     - `width`/`height` as fixed px where source was `%`/`auto`/`max-width`-governed: confirm "fixed px or keep it fluid?" rather than baking px and breaking responsiveness.
     - `background-color`/`color` **absent** where you'd expect one: the overlay shows a transparent colour as `#000000` in the swatch and treats clicking that shown value as a no-op revert, so no patch is emitted even if the user meant to set solid black. If a black background/colour is clearly intended (e.g. visible in a screenshot) but no patch is present, ask before writing one.
     - `width`/`height` on a non-replaced `inline` element: the overlay disables these inputs and the resize grips for inline elements, so this patch can no longer be emitted. If you see one in an older edits file, skip it and note it ("dropped width on inline `<code>` - needs `display:inline-block` first").
   - `nudge {dx, dy}` → clean spacing. The offset is a `translate(dx, dy)`, so **positive dx = moved right, positive dy = moved down**. Map to margins with the matching sign: `dy>0` (down) → add to `margin-top`; `dy<0` (up) → reduce `margin-top` (go negative if needed); `dx>0` (right) → add to `margin-left`; `dx<0` (left) → reduce `margin-left`. Worked example: `nudge {dx: 0, dy: -8}` means dragged up 8px → take 8px off `margin-top` (e.g. `margin: 20px 0` → `margin: 12px 0`). Never bake in `transform` or `position: absolute`. If the nudge is large or flow cannot express it, flag it as a v2 reorder and skip it.
6. **Check responsiveness.** The batch `viewport` is the width the edits were authored at. If a width/size change made at a wide viewport would obviously break mobile, warn and offer to scope it to a media query.
7. **Write** the CSS into the stylesheet already governing the element, in house conventions. Show a concise diff summary.
8. **Mark done.** `scripts/wtreconcile.py mark <file> <sessionId>` flips that batch to `reconciled` (timestamped); it stays in the file as history, never delete it. On success it prints `marked N batch(es) reconciled` (N≥1) and exits 0; on a wrong/unknown sessionId it prints `... nothing marked` to stderr and exits non-zero. Treat a non-zero exit (or the absence of a `marked N` success line) as: nothing was flipped, so the edits are still pending and would re-apply next run - resolve that before telling the user it's done.
9. **Stop at source.** Reconcile's job ends at writing source and marking the batch. Never push, commit, or deploy unless the user explicitly asks for it in this session - summarise what changed and let them decide.

## The `create` op

A create patch inserts a brand-new decorative shape (square, rectangle, circle, ellipse, triangle, star, diamond, pentagon, hexagon) that the user drew on the page. This is the one place reconcile *adds* source rather than restyling it. Shape:

```
{ op: "create", shape: "triangle", renderer: "svg",
  geometry: { viewBox: "0 0 100 100", el: "polygon", points: "50,0 100,100 0,100", attrs: null },
  anchor: { parent: <fingerprint>, position: "append" },
  fingerprint: <fingerprint of the drawn <svg>, carrying a throwaway wt-shape-<rand> id>,
  changes: { position, left, top, width, height, fill, stroke, stroke-width, rx? } }
```

The overlay renders every shape as one inline `<svg class="wt-shape">` wrapping a single child primitive (`geometry.el` = `rect` | `ellipse` | `polygon`), drawn into a fixed `0 0 100 100` viewBox with `preserveAspectRatio="none"`. `fill`/`stroke`/`stroke-width` are inherited SVG presentation properties set on the `<svg>` so they cascade to the child; `rx` (rect/square corner radius only) is a `<rect>` geometry property and is meant for the child node.

**Write a clean element + clean CSS:**
1. **Insert the element** at the anchor. Default: append a single `<svg>` near the end of `<body>` (`anchor.parent` fingerprints where webtweak placed it - usually `body`; honour it if it cleanly maps to a source container, else fall back to end-of-`<body>` and say so). Build the child from `geometry` (`el` + `points` for polygons, or `attrs` for rect/ellipse), keep `viewBox="0 0 100 100"`, `preserveAspectRatio="none"`, and `vector-effect="non-scaling-stroke"` on the child so the stroke stays even when stretched.
2. **Strip the `wt-shape-<rand>` id.** It is a throwaway overlay handle, never source identity. Give the element a clean, intention-revealing hook instead - a `.shape-…` class with a rule in the stylesheet (house style), or a semantic id if the site uses ids. Drop the `wt-shape` class too; it is overlay-internal.
3. **Map the style.** `fill`/`stroke`/`stroke-width` go on the `<svg>` (they cascade); `rx` goes on the child `<rect>`. `position`/`left`/`top`/`width`/`height` set the absolute placement and size. Prefer a CSS rule over a fat inline `style` (match how the site handles its other decorative elements); a small inline `style` for the one-off position is acceptable if the site has no decorative-layer convention - ask if unsure.
4. **Absolute placement is sanctioned here.** A create patch is the documented exception to the "never bake `position: absolute`" rule (that rule governs flow content + nudges, per ADR-0001). A decorative shape is a genuine absolute layer, so `position: absolute; left; top` is the *correct* output, not a hack. (Contrast a `nudge`, which still reconciles to clean margin/padding.) Consider whether the shape should be positioned relative to a sensible containing block - if `anchor.parent` is a positioned container, scope it there; if it is loose on `<body>`, that is fine for a page-level decoration but worth a one-line note.
5. **Ask when ambiguous**, exactly as for edit patches: if placement/containing-block or the scope (one-off vs a reusable `.shape-star` utility) is genuinely unclear, STOP and ask rather than guess. Watch the batch `viewport` for responsiveness - a shape pinned at desktop pixels may need a media-query or a percentage-based position on mobile; flag it.

Mark the batch reconciled with the helper exactly as for edit patches.

## Helper script

`scripts/wtreconcile.py` (Python stdlib only):

- `pending <file>` - one-line summary per pending patch; add `--full` for the complete patch JSON (fingerprints + changes)
- `mark <file> [sessionId]` - flip the matching pending batch to `reconciled` with a timestamp. Omitting the sessionId marks the single pending batch, but **fails** (marks nothing) if more than one is pending, so reconciling one session can't silently retire another. Prints `marked N` + exits 0 on success; exits non-zero and marks nothing on a no-match or an ambiguous bare `mark`.
- `status <file>` - counts (pending vs reconciled) + newest pending save time, for a quick "is this file fully reconciled?" check
