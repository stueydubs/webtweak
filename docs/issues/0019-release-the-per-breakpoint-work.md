# Issue 0019: Release the per-breakpoint work - recorded scope, changelog, version, demo

> **Shipped** as 0.7.0, 2026-08-01. The demo turned out to be a bigger job than "re-record":
> it is a hand-built React re-creation of the overlay (Remotion), not a screen capture, so
> a control added to the real bar has to be added to the demo by hand or the video quietly
> goes a release out of date - which is exactly how it got stale. It had also been
> re-recorded once already at `302e2bb`, the commit immediately BEFORE the epic began, so
> the issue's own claim that it predated 0.4.0 was wrong while its conclusion was right.
> The bar gained the Scope picker, Shape and Reset all; the panel gained the Align row; the
> code panes now show the `media` map and the `@media` block reconcile writes from it. A
> bug in the demo's CSS tokenizer surfaced doing it - it stripped only the first `{`, so a
> nested rule rendered as `h1.title  font-size: 32px; } {`.

> Labels: chore, ready-for-agent · Type: AFK

## Parent

[PRD: per-breakpoint authoring](../PRD-per-breakpoint-authoring.md)

## What to build

The release, plus the documentation that ships false the moment the code lands - and this time that includes the tool's own marketing.

**The single-viewport limitation is stated in four places** and every one of them stops being true: `CONTEXT.md`'s recorded decision ("v1 is single-viewport editing - changes are base CSS"), the README's opening summary ("It is *not* a responsive-design tool"), the README's "What v1 does not do" list, and `docs/PRD.md`'s deferred-features section. Each needs rewriting to what is now true, including the parts that remain true: you still author at widths your own screen can show, and webtweak still does not invent breakpoints your site does not have.

**Breakpoint joins the glossary**, as the band an edit is scoped to, distinct from the batch's `viewport` stamp - which is a different thing (the width the session happened at) and will otherwise be conflated with it by the next reader.

**The Patch contract changed**, so the release notes lead with that: an edits file written by this release needs a skill from it to reconcile its banded patches, and existing users must reinstall the bundled skill. An older edits file still reconciles unchanged, and saying so is what stops the change reading as a break.

**The demo video is stale.** `site/demo.mp4` and `demo-poster.png` were recorded before 0.4.0, so they show a panel with no Border group and no history buttons, and now also no band picker. The landing page is the first thing a prospective user sees; a demo two releases behind undersells the tool and reads as abandonment. Re-record from `site/src/` (Remotion). Note `pages.yml` is path-filtered to `site/**`, so the site only redeploys when those files change.

## Acceptance criteria

- [x] `CONTEXT.md`'s single-viewport decision is rewritten, and Band is in the glossary as distinct from the viewport stamp
- [x] The README no longer says webtweak is not a responsive-design tool, and its limitations list describes the real remaining limits
- [x] `docs/PRD.md`'s deferred list reflects that per-breakpoint authoring has shipped
- [x] CHANGELOG has a section for this release covering discovery, the picker, scoped preview and recording, reconcile's media merging, and restore, with its compare links extended
- [x] The release notes state the Patch contract change, that older edits files are unaffected, and that the skill must be reinstalled
- [x] The version is bumped (minor - the Patch contract gains a dimension)
- [x] The demo video and poster show the current overlay
- [x] The full suite passes, including the browser job
- [x] The packaged tarball is smoke-tested: packed, installed from the artefact into a clean project, run against a page, overlay assets served (they are served flat under `/__webtweak__/`, not under `overlay/`), and driven in a real browser - the band picker offered the fixture's own conditions, a banded edit rendered at 480px and not at 1280px, and the written patch carried its `media` map. Zero page errors.
- [x] Publishing and pushing are left for explicit sign-off

## Blocked by

- Issue 0014 (Breakpoint discovery and the band picker)
- Issue 0015 (Breakpoint-scoped preview and recording)
- Issue 0016 (Reconcile merges banded changes into the page's own media queries)
- Issue 0017 (Banded edits survive a reload)
- Issue 0018 (Document the local browser-test setup)
