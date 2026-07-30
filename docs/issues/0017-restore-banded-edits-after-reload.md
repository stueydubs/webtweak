# Issue 0017: Banded edits survive a reload

> Labels: enhancement, ready-for-agent · Type: AFK

## Parent

[PRD: webtweak 0.6.0](../PRD-0.6.0.md)

## What to build

A reload mid-session already restores the current session's pending edits, and that promise has to keep holding once edits carry a band. The failure it prevents is specific: restoring a banded edit as inline style would make a mobile-only change apply at **every** width, and the user would have no way to tell from the page that their responsive work had been flattened.

So `restore()` re-applies each patch's `media` groups through the injected `<style>` block and its generated classes - the same path Issue 0015 built for a live edit - and only `changes` goes on as inline style. An element restored with both gets both.

The live-reload safety rules are unchanged and must stay unchanged: no reload over unsaved edits, none while this session's batch is still pending, and webtweak's own writes never bounce the page. This ticket adds no new reload trigger; it only changes what a restore *applies*.

Two existing behaviours need re-checking against the new shape, because both were written when a patch had one flat set of changes:

- **The unrelocatable-patch path.** A patch whose element cannot be found is preserved across saves rather than dropped. A banded patch must be preserved whole, bands included, not reduced to its base changes.
- **The revert-after-reload baseline.** The panel recovers a true authored baseline by reading computed style with the override peeled off. With a band selected, the override to peel is the injected rule, not the inline style - so a restored banded edit set back to its authored value must still be recognised as a revert and clear the batch.

## Acceptance criteria

- [ ] After a reload, a banded edit still applies at a width inside its band
- [ ] After a reload, that same edit does not apply at a width outside its band
- [ ] An element with both a base and a banded change restores both
- [ ] A restored banded edit re-saves identically, producing no duplicate or drifted patch
- [ ] A banded patch whose element cannot be relocated is preserved whole across a save, bands included
- [ ] Setting a restored banded edit back to its authored value is recognised as a revert and clears it
- [ ] The existing reload-safety rules still hold, with their existing tests unmodified
- [ ] Browser tests cover the above, asserting at two widths, and carry the browser marker

## Blocked by

- Issue 0015 (Breakpoint-scoped preview and recording) - for the applied and recorded shape
