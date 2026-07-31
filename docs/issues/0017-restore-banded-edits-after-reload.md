# Issue 0017: Banded edits survive a reload

> Labels: enhancement, ready-for-agent · Type: AFK

## Parent

[PRD: per-breakpoint authoring](../PRD-per-breakpoint-authoring.md)

## What to build

A reload mid-session already restores the current session's pending edits, and that promise has to keep holding once edits carry a band. The failure it prevents is specific: restoring a banded edit as inline style would make a mobile-only change apply at **every** width, and the user would have no way to tell from the page that their responsive work had been flattened.

So `restore()` re-applies each patch's `media` groups through the injected `<style>` block and its generated classes - the same path Issue 0015 built for a live edit - and only `changes` goes on as inline style. An element restored with both gets both.

The live-reload safety rules are unchanged and must stay unchanged: no reload over unsaved edits, none while this session's batch is still pending, and webtweak's own writes never bounce the page. This ticket adds no new reload trigger; it only changes what a restore *applies*.

Two existing behaviours need re-checking against the new shape, because both were written when a patch had one flat set of changes:

- **The unrelocatable-patch path.** A patch whose element cannot be found is preserved across saves rather than dropped. A banded patch must be preserved whole, bands included, not reduced to its base changes.
- **The revert-after-reload baseline.** The panel recovers a true authored baseline by reading computed style with the override peeled off. With a band selected, the override to peel is the injected rule, not the inline style - so a restored banded edit set back to its authored value must still be recognised as a revert and clear the batch.

- **A hand-typed Band was not restored into the picker** - found during the 0016 integration sweep, and **fixed**. `manualBands` was written only by the manual-entry path, so after a reload a Band the user typed by hand was no longer offered in the Scope picker even though its edit had restored correctly and still previewed and saved. The edit was intact; it just could not be re-selected, so it could not be revisited or reverted through the Scope control without retyping the exact condition. Both routes to such a condition now go through one `rememberBand()` helper - typed into the picker, or restored from a saved patch - and a browser test covers it (`test_a_hand_typed_band_is_still_offered_after_a_reload`), asserting the restored edit is still *conditional* as well as that its band is back, since a test reading only the list would pass against a restore that had flattened the edit to base.

## Acceptance criteria

- [x] After a reload, a banded edit still applies at a width inside its band
- [x] After a reload, that same edit does not apply at a width outside its band
- [x] An element with both a base and a banded change restores both
- [x] A restored banded edit re-saves identically, producing no duplicate or drifted patch
- [x] A banded patch whose element cannot be relocated is preserved whole across a save, bands included
- [x] Setting a restored banded edit back to its authored value is recognised as a revert and clears it
- [x] A hand-typed Band is still selectable in the Scope picker after a reload
- [x] The existing reload-safety rules still hold, with their existing tests unmodified
- [x] Browser tests cover the above, asserting at two widths, and carry the browser marker

## Outcome

Eight of the nine criteria were open, and seven of them turned out to need only a
test: `restore()`'s banded path had been written alongside 0015, because restoring
has to undo whatever `save()` did, and it was correct. What was missing was any proof
that a reload round-trip preserved a band, and an untested promise is not a kept one.

`tests/test_e2e_banded_reload.py` covers them: applies-inside/not-outside on a band
the page declares (the hand-typed case was already covered in
`test_e2e_banded_edits.py`), base-and-band on one element, the re-save round-trip,
the stranded banded patch, and the revert-to-baseline check. Each asserts at two
widths, per the PRD's testing decision, and the first also asserts the condition the
Overlay actually re-registered - two widths can bracket a band but cannot pin it, and
a restore that widened `(max-width: 600px)` to 1100px passed everything until that
assertion existed.

**The ninth criterion was genuinely not met**, and a QA round found it after the
first pass had been committed as done. A stranded patch - one whose element could not
be confirmed - was dropped whole when the user then edited an element with the same
id, on the rule that a fresh patch supersedes it. True per declaration, false per
patch: every property the fresh patch happened not to set went with it, silently,
having just been reported as "kept for reconcile". The first test of this used
`#ghost`, an id nothing on the page can match, so it proved only the half that could
not collide. `save()` now carries stranded declarations over wherever the fresh patch
has no value for that property and band - the same wrong-granularity fix reconcile's
step 6 needed - with tests for both directions.

**Writing the tests also surfaced a defect elsewhere**: three of the first five timed
out because Save sat outside the viewport once anything had been saved. That, the
shape palette covering bar controls once the bar wrapped, and the change-list header
sliding under it are all recorded in CHANGELOG.

## Blocked by

- Issue 0015 (Breakpoint-scoped preview and recording) - for the applied and recorded shape
