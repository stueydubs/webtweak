---
name: webtweak-reconcile
description: Reconcile visual edits captured by the webtweak tool into a site's real source. Reads a <page>.webtweak.json edits file, locates each patched element by its fingerprint, writes clean CSS in the site's house conventions (single-element scope by default), translates nudge intent into clean margin/padding, and marks batches reconciled. Use when the user has finished a webtweak session, says "reconcile my webtweak edits", "apply the webtweak changes", mentions a *.webtweak.json file, or wants webtweak edits folded into source and optionally pushed.
---

# webtweak reconcile

The second half of the webtweak loop. The webtweak tool (`~/projects/webtweak`) captures visual edits as *intent* and never touches source; this skill turns that intent into clean source. Reconcile is judgment work - when a match or a scope decision is genuinely ambiguous, ask rather than guess. That is the whole reason this half is a skill and not code.

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
2. **Read the house style.** Open the stylesheet(s) governing the page. Note indentation, selector conventions, units, custom properties, and British spelling - match them.
3. **Locate each element.** Resolve the fingerprint the way a human would, in priority order: `id` (before accepting, confirm the located element's `tag` matches `fingerprint.tag` - guards a stale id moved to a different element) → `classes` + `ownText`/`text` (+ `tag`) → `openTag`. Use `selector` only as a last-resort tiebreaker or confirmation, never as a primary locator - it is a positional `nth-of-type` path captured on the injected DOM, so it is the least trustworthy signal and can be stale. If two candidates still match equally well (identical siblings), use `siblingIndex` to name which one; if it is still genuinely ambiguous, STOP and ask - never guess. **If nothing matches at all**, do not invent a target: source can be hand-edited between capture and reconcile, so a vanished element is expected, not exceptional. Report that patch unresolved and leave it - per step 8 it blocks marking the batch.

   Matching note: `text` and `ownText` are whitespace-collapsed and truncated to 80 characters, and `openTag` to 300. Match them as a normalised **prefix**, never by string equality, or a long paragraph will never match its own source.
4. **Decide scope** (per patch). Default: change only the element that was edited. If it is targeted by a shared class AND the change looks systemic (every sibling changed alike, or it is the sole instance of that class), ask "just this one, or all `.class`?". If single-element scope needs a selector hook the source lacks, prefer the captured `selector`; only add a class to the HTML after asking.
5. **Translate the changes.**
   - Plain CSS props → write as-is into the governing rule (or a targeted rule for single-element scope). One gotcha: a multi-word `font-family` may arrive unquoted (e.g. `font-family: Helvetica Neue`) - quote the family name on write (`"Helvetica Neue"`) so the CSS is valid.
   - **`border` arrives as one composed declaration** (e.g. `border: 1px solid #ff0000`) built from three panel controls, and it may carry a width or style the user never individually chose. That is deliberate, not a bug: on an element with no border, a colour alone and a width alone both render nothing, so the overlay seeds the other parts and previews the result - the declaration is exactly what was on screen (ADR-0003). Write it as one declaration; tidy it into house conventions (a custom property for the colour, the site's usual border width) but do **not** split it into `border-width`/`border-style`/`border-color` longhands unless the source already uses them. `border: none` means remove the border.
   - **A per-side `border-bottom` / `border-top` / `border-left` / `border-right` is deliberate - never normalise it into an all-sides `border`.** The overlay emits a per-side declaration only when the element it edited had a visible border on exactly that one side (a rule under a heading, a line above a footer). **The side is the intent.** "Tidying" `border-bottom: 2px solid #7a5c3e` into `border: 2px solid #7a5c3e` turns a divider into a box - a silent, destructive edit, and the exact outcome the overlay went out of its way to avoid. Keep the side, and keep it on the side named.
   - **`border-radius`** is an ordinary single value. If the source authored per-corner radii (`border-radius: 12px 12px 0 0`), the patch's single value would flatten all four corners - ask rather than flatten.
   - **`box-shadow`** normally arrives as authored (a picked preset or a typed value, e.g. `0 8px 24px rgba(0, 0, 0, 0.18)`). But the field is populated from computed style, so if the user edited an existing shadow in place it can arrive **colour-first** (`rgba(0, 0, 0, 0.18) 0px 8px 24px 0px`) - valid CSS, but not how anyone writes it. Rewrite it offset-first in the site's own order, and drop a redundant trailing `0px` spread.
   - **Suspect computed-not-authored values** (per the Input caveat) - check each against the source declaration before writing, don't bake the resolved value:
     - `line-height` as px (e.g. `33.6px`): if source authored a unitless ratio or em, keep that form - recompute the ratio from the new px ÷ the element's font-size, or ask for the ratio. Same for em `letter-spacing`.
     - `margin`/`padding` as 4-value px where source had `auto` (centering) or `%`: preserve the `auto`/`%`; only change the side(s) the user actually moved, not the whole shorthand.
     - `width`/`height` as fixed px where source was `%`/`auto`/`max-width`-governed: confirm "fixed px or keep it fluid?" rather than baking px and breaking responsiveness.
     - `background-color`/`color` **absent** where you'd expect one: the overlay shows a transparent colour as `#000000` in the swatch and treats clicking that shown value as a no-op revert, so no patch is emitted even if the user meant to set solid black. If a black background/colour is clearly intended (e.g. visible in a screenshot) but no patch is present, ask before writing one.
     - `width`/`height` on a non-replaced `inline` element: the overlay disables these inputs and the resize grips for inline elements, so this patch can no longer be emitted. If you see one in an older edits file, skip it and note it ("dropped width on inline `<code>` - needs `display:inline-block` first").
   - `nudge {dx, dy}` → clean spacing. The offset is a `translate(dx, dy)`, so **positive dx = moved right, positive dy = moved down**. Map to margins with the matching sign: `dy>0` (down) → add to `margin-top`; `dy<0` (up) → reduce `margin-top` (go negative if needed); `dx>0` (right) → add to `margin-left`; `dx<0` (left) → reduce `margin-left`. Worked example: `nudge {dx: 0, dy: -8}` means dragged up 8px → take 8px off `margin-top` (e.g. `margin: 20px 0` → `margin: 12px 0`). Never bake in `transform` or `position: absolute`.
     - **Apply every nudge. A small offset is intent, not drag jitter.** The overlay snaps to a 4px grid before recording, so noise cannot survive capture - a 4px or 8px nudge is a deliberate choice the user made by eye and expects to see. Never dismiss one as too small to matter, and never silently drop one.
     - `position: relative` with `top`/`left` is an acceptable clean form where flow genuinely cannot express the offset (a centred fixed-height band, a flex item whose margin is doing other work). It is *not* the banned `position: absolute`/`transform` hack - the ban is on taking an element out of flow, not on nudging it within flow.
     - If a nudge is large enough to be a reorder, or you cannot find a clean form for it, **ask** - do not skip it silently. Per step 8, an unresolved patch blocks marking the batch.
6. **Check responsiveness.** The batch `viewport` is the width the edits were authored at. If a width/size change made at a wide viewport would obviously break mobile, warn and offer to scope it to a media query.
7. **Write** the CSS into the stylesheet already governing the element, in house conventions. Show a concise diff summary.
8. **Account for every patch, then mark done.** First list each patch in the batch with its outcome: **applied** (and where), **skipped** (and why), or **awaiting your answer**. Marking flips the *whole batch*, and a reconciled batch is never re-applied - so anything not applied is silently retired the moment you mark. **If any patch was skipped or is awaiting an answer, do NOT mark the batch.** Leave it pending, say which patches are outstanding, and resolve them first.

   Once every patch is accounted for: `scripts/wtreconcile.py mark <file> <sessionId>` flips that batch to `reconciled` (timestamped); it stays in the file as history, never delete it. On success it prints `marked N batch(es) reconciled` (N≥1) and exits 0; on a wrong/unknown sessionId it prints `... nothing marked` to stderr and exits non-zero. Treat a non-zero exit (or the absence of a `marked N` success line) as: nothing was flipped, so the edits are still pending and would re-apply next run - resolve that before telling the user it's done.
9. **Verify before you claim it's done.** After writing, re-read the region you wrote: confirm each declaration is actually present, that its selector really matches the located element, and that no later rule in the cascade overrides it. A rule written into a stylesheet that the cascade then overrides renders nothing while the record claims success. Reload the page and look before step 8.
10. **Stop at source.** Reconcile's job ends at writing source and marking the batch. Never push, commit, or deploy unless the user explicitly asks for it in this session - summarise what changed and let them decide. For client sites with a no-push rule (e.g. Walker Scientific) this is doubly firm: express written permission only.

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
