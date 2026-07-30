# Issue 0015: Breakpoint-scoped preview and recording

> Labels: enhancement, ready-for-agent · Type: AFK

## Parent

[PRD: per-breakpoint authoring](../PRD-per-breakpoint-authoring.md)

## What to build

The release's centre, and the one item that should be built and reviewed entirely on its own. An edit made while a band is the editing target previews **only in that band** and records **under that band's condition**.

An inline `style` attribute cannot carry a media query, so the existing preview mechanism cannot express this edit at all. The Overlay instead maintains one injected `<style>` element holding real `@media` blocks, and gives each element it edits in a band a generated `wt-mq-N` class to target. A browser prototype confirmed the behaviour that matters: the rule applies at 480px and does not apply at 700px or 1280px, so what the user sees is conditional in exactly the way the Patch will claim.

The generated class must never reach a Fingerprint. `nonWtClasses` strips only the exact names registered in `WT_OWN_CLASSES` - deliberately not a `wt-` prefix match, because a prefix match would erase a page's own `wt-` design-system classes from its identity - so each generated class is registered there as it is created.

The Patch gains a media dimension: `changes` continues to carry base declarations, and a sibling `media` map carries one group of declarations per condition. A patch with no `media` key is byte-identical to what 0.4.0 wrote, so the format change is additive.

**Everything keyed by `el + prop` needs the band as part of its key**, and this is where the release's silent failure lives. `font-size` at base and `font-size` at `(max-width: 600px)` are two different recorded values on the same element and the same property. Undo, the change list, the revert-to-baseline check and the unsaved-changes flag all currently assume one value per element per property. A banded edit that overwrote a base edit would still produce a valid-looking Patch - the same shape of bug ADR-0003 named for composed borders, and it wants the same answer: mutation-test the cases where a plausible wrong result is indistinguishable from a right one.

The panel needs no new reading machinery. `getComputedStyle` already resolves the page's own media queries at the current width, which a prototype confirmed against the fixture's headline: 44px at 1280px, 32px at 480px. The baseline peel, however, must peel the injected rule rather than the inline style when the target is a band.

## Acceptance criteria

- [ ] An edit made with a band selected applies at a width inside that band
- [ ] The same edit does not apply at a width outside that band
- [ ] The edit records under its condition in the patch's `media` map, not in `changes`
- [ ] A base edit made at a narrow width still records in `changes`
- [ ] The same property edited at base and in a band records both values, neither overwriting the other
- [ ] The generated preview class does not appear in the patch's Fingerprint classes
- [ ] The change list distinguishes a banded change from a base one on the same element
- [ ] Undo steps back through a banded edit without disturbing a base edit on the same property
- [ ] Clearing a banded field reverts only that band
- [ ] Setting a banded field back to the value the band already renders records nothing
- [ ] A patch carrying no band is unchanged from 0.4.0's output
- [ ] Browser tests cover the above, asserting at two widths, and carry the browser marker

## Blocked by

- Issue 0014 (Breakpoint discovery and the band picker) - for the editing target
