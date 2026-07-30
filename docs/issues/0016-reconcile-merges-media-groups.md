# Issue 0016: Reconcile merges banded changes into the page's own media queries

> Labels: enhancement, ready-for-agent · Type: AFK

## Parent

[PRD: webtweak 0.6.0](../PRD-0.6.0.md)

## What to build

Claude's half of the loop learns the media dimension. A patch carrying a `media` map is reconciled into the media query the stylesheet **already has**, so a site's CSS does not sprout a second `@media (max-width: 600px)` block below the first.

Three rules, and the middle one is the subtle one:

1. **Merge into the existing block** for that condition - the same single-element-scope and house-convention rules that already govern base declarations apply inside it.
2. **Never reorder media blocks.** Media query order is cascade order, so moving a block changes which rule wins on widths where two conditions overlap. A reconcile that tidies blocks into ascending-width order can silently change the rendering of pages it did not touch.
3. **Create a block only when the page genuinely has none** for that condition, placed by the site's own convention - usually after the base rules it modifies, matching where the page keeps its other queries.

The skill also needs to say what a banded patch means about intent: the user chose that condition explicitly and watched the change appear and disappear as they resized, so the condition is not a hint to be improved on. Widening `(max-width: 600px)` to `(max-width: 768px)` because the site uses 768 elsewhere is the same class of edit as normalising a per-side `border-bottom` into an all-sides `border` - a tidy-up that destroys the intent.

The batch's `viewport` stamp keeps its existing job for base patches (warn when a base change authored wide would obviously break narrow) and needs restating so it is not read as redundant: a banded patch needs no such warning, because the user said which width they meant.

Documentation only in the bundled skill, plus whatever of it is scriptable in `reconcile/scripts/wtreconcile.py` and its tests.

## Acceptance criteria

- [ ] The skill documents the `media` map: its shape, and that an absent key means a base-only patch
- [ ] The skill states that a banded change merges into the existing block for that condition
- [ ] The skill states that media blocks are never reordered, and why (cascade order)
- [ ] The skill states that a new block is created only when none exists, and where to place it
- [ ] The skill states that the chosen condition must not be "improved" to a nearby one the site uses elsewhere
- [ ] The skill's account of the `viewport` stamp distinguishes base from banded patches
- [ ] `wtreconcile.py`'s pending-summary output reports banded patches legibly, and its tests cover a banded batch
- [ ] Existing edits files with no `media` key are unaffected, with a test proving it

## Blocked by

- Issue 0015 (Breakpoint-scoped preview and recording) - for the emitted patch shape
