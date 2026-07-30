# Issue 0019: Release 0.6.0 - recorded scope, changelog, version, demo

> Labels: chore, ready-for-agent · Type: AFK

## Parent

[PRD: webtweak 0.6.0](../PRD-0.6.0.md)

## What to build

The release, plus the documentation that ships false the moment the code lands - and this time that includes the tool's own marketing.

**The single-viewport limitation is stated in four places** and every one of them stops being true: `CONTEXT.md`'s recorded decision ("v1 is single-viewport editing - changes are base CSS"), the README's opening summary ("It is *not* a responsive-design tool"), the README's "What v1 does not do" list, and `docs/PRD.md`'s deferred-features section. Each needs rewriting to what is now true, including the parts that remain true: you still author at widths your own screen can show, and webtweak still does not invent breakpoints your site does not have.

**Breakpoint joins the glossary**, as the band an edit is scoped to, distinct from the batch's `viewport` stamp - which is a different thing (the width the session happened at) and will otherwise be conflated with it by the next reader.

**The Patch contract changed**, so the release notes lead with that: an edits file written by 0.6.0 needs a 0.6.0-era skill to reconcile its banded patches, and existing users must reinstall the bundled skill. An older edits file still reconciles unchanged, and saying so is what stops the change reading as a break.

**The demo video is stale.** `site/demo.mp4` and `demo-poster.png` were recorded before 0.4.0, so they show a panel with no Border group and no history buttons, and now also no band picker. The landing page is the first thing a prospective user sees; a demo two releases behind undersells the tool and reads as abandonment. Re-record from `site/src/` (Remotion). Note `pages.yml` is path-filtered to `site/**`, so the site only redeploys when those files change.

## Acceptance criteria

- [ ] `CONTEXT.md`'s single-viewport decision is rewritten, and Breakpoint is in the glossary as distinct from the viewport stamp
- [ ] The README no longer says webtweak is not a responsive-design tool, and its limitations list describes the real remaining limits
- [ ] `docs/PRD.md`'s deferred list reflects that per-breakpoint authoring has shipped
- [ ] CHANGELOG has a 0.6.0 section covering discovery, the picker, scoped preview and recording, reconcile's media merging, and restore, with its compare links extended
- [ ] The release notes state the Patch contract change, that older edits files are unaffected, and that the skill must be reinstalled
- [ ] The version is bumped to 0.6.0
- [ ] The demo video and poster show the current overlay
- [ ] The full suite passes, including the browser job
- [ ] The packaged tarball is smoke-tested: installed from the registry, run against a page, overlay assets served
- [ ] Publishing and pushing are left for explicit sign-off

## Blocked by

- Issue 0014 (Breakpoint discovery and the band picker)
- Issue 0015 (Breakpoint-scoped preview and recording)
- Issue 0016 (Reconcile merges banded changes into the page's own media queries)
- Issue 0017 (Banded edits survive a reload)
- Issue 0018 (Document the local browser-test setup)
