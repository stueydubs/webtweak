# PRD: webtweak v1

> Status: needs-triage
> A local, open-source visual editor for hand-coded HTML/CSS pages. Half of a human-plus-Claude loop: webtweak captures visual edit *intent*; Claude reconciles it into real source. See [CONTEXT.md](../CONTEXT.md) and [ADR-0001](./adr/0001-capture-intent-not-rewrite-source.md).

## Problem Statement

When refining a hand-coded editorial site, the spatial work - "make this heading bigger", "tighten that spacing", "nudge this down a touch", "try a different font here" - is far faster to do by eye with a mouse than to describe in words. Today that means a stream of small text nudges to Claude, each a round-trip, each an approximation of something I could just *show* in one drag. Paid tools (Pinegrow, US$99/yr) solve this but carry a source-preserving HTML parser I don't need, and no free/open-source tool edits existing static HTML files with proper drag-and-drop (Silex builds new sites in its own format; Onlook is React-only).

## Solution

A tiny local tool - `webtweak <page.html>` - that opens my actual source page in the browser with an editing Overlay on top. I select elements and visually resize them, restyle them (fonts, colours, spacing, alignment), and nudge their position. webtweak captures each change as a machine-readable Patch (a rich element Fingerprint plus the property/value changes) and writes it to a running-history edits file next to the page. I then tell Claude "I've adjusted X", and Claude reconciles the Patches into the real source - clean CSS in house conventions - and pushes. The tool only has to capture intent; Claude does the judgment-heavy work of locating elements and writing good CSS. That asymmetry is what makes it small enough to own.

## User Stories

1. As a site builder, I want to open a local source HTML page in a visual editor with one command, so that I can edit the exact file I will push without a build step or upload.
2. As a site builder, I want the page to render with its real CSS, images, and fonts, so that what I see matches production.
3. As a site builder, I want to hover over the page and see which element I am about to select highlighted, so that I can target precisely.
4. As a site builder, I want to click an element to select it and see a breadcrumb of where it sits in the structure, so that I know exactly what I am editing.
5. As a site builder, I want to drag a selected element's handles to resize it, so that I can set width and height by eye.
6. As a site builder, I want to drag a selected element to nudge its position, so that I can fine-tune placement spatially instead of guessing pixel values.
7. As a site builder, I want nudges to snap to a 4px grid, so that the resulting values stay tidy.
8. As a site builder, I want to change a selected element's font family, size, weight, line-height, and letter-spacing, so that I can tune typography visually.
9. As a site builder, I want to change a selected element's text colour and background colour, so that I can adjust palette by eye.
10. As a site builder, I want to change a selected element's text alignment, margin, and padding, so that I can control layout and spacing.
11. As a site builder, I want every change to preview live on the page, so that I get immediate feedback.
12. As a site builder, I want to save my session with one click, so that my changes are written to disk for Claude to read.
13. As a site builder, I want each saved change to carry a rich fingerprint of its element (tag, id, classes, text, selector, opening tag), so that Claude can reliably locate it in the real source without me injecting IDs.
14. As a site builder, I want my edits stored as a running history of batches rather than overwritten, so that I keep a permanent changelog of every visual change to the page.
15. As a site builder, I want re-saving within one session to overwrite that session's batch rather than pile up duplicates, so that a batch is a clean snapshot.
16. As a site builder, I want the viewport width recorded with each batch, so that Claude can warn me when a desktop-width change would break mobile.
17. As Claude (the reconciler), I want to read only pending batches, so that I never re-apply changes I have already pushed.
18. As Claude, I want each patch to express position nudges as snapped intent rather than literal transforms, so that I can translate them into clean margin/padding CSS instead of baking in floating-element hacks.
19. As Claude, I want changes scoped by default to the single element edited, so that I do not accidentally ripple a one-off tweak across every element sharing a class.
20. As a site builder, I want webtweak to touch nothing in my source until Claude deliberately reconciles, so that the tool is safe to run against a clean codebase.
21. As a site builder, I want the tool to run on Python stdlib with no install step, so that I can use it anywhere without dependency management.
22. As a site builder, I want the editor to work fully offline, so that it never breaks when a CDN changes.
23. As a site builder, I want to stop the editor with Ctrl-C and have my source unchanged, so that running webtweak is consequence-free until I choose to reconcile.

## Implementation Decisions

- **Architecture: capture-intent, not rewrite-source.** webtweak emits Patches for an intelligent reconciler (Claude); it never writes the page's source itself. (ADR-0001.)
- **Input is local source files**, served from the target page's own directory so assets resolve as in production. No live-URL mode in v1.
- **Stack: Python stdlib only**, single `webtweak` executable over `http.server` / `ThreadingHTTPServer`. interact.js is vendored under `overlay/` (not CDN-loaded) for offline use.
- **Overlay injection.** The server injects the Overlay (`overlay.css`, vendored `interact.min.js`, `overlay.js`, plus a config object naming the target page) before `</body>` of served HTML. Overlay assets are served under a reserved `/__webtweak__/` path so they never collide with project files.
- **Deep module `inject_overlay(html, target_name) → html`** - pure function inserting the Overlay markup before the last `</body>`; appends if none found.
- **Deep module `apply_batch(doc, payload, now) → doc`** - pure function implementing running-history semantics: locate the pending batch matching the payload's `sessionId` and replace it, else append a new pending batch; stamp `savedAt` and `viewport`; default `status: "pending"`. Extracted out of the request handler so it is unit-testable without HTTP.
- **Element identity is a rich Fingerprint** (tag, id, classes minus `wt-*`, truncated text, best-effort `cssPath` selector, clean opening tag with the injected inline `style` stripped). No injected attributes; source untouched until reconcile.
- **`cssPath(el)`** builds an `nth-of-type` selector path, stopping at the nearest id or `body`.
- **Position nudges** are captured as a snapped (4px) `{dx, dy}` offset previewed via `transform: translate(...)`; resize is captured as `width`/`height`. Resize edges are limited to right and bottom in v1 so resizing never moves the element origin (no translate/nudge conflation).
- **edits file** is `<page-stem>.webtweak.json` written next to the target page: `{ target, batches: [ { sessionId, savedAt, viewport, status, patches: [ { fingerprint, changes } ] } ] }`.
- **Save endpoint** is `POST /__webtweak__/save`; the handler delegates to `apply_batch` and writes the file.
- **CLI**: `webtweak <path-to-html> [--port 8723] [--no-browser]`; auto-opens the browser; symlinked onto PATH.
- **Reconcile is out of band** - performed by Claude (eventually wrapped in a companion skill), not by this codebase. Default scope is single-element; systemic-looking changes are flagged to the user; reconcile writes real CSS rules into the existing governing stylesheet, never inline.

## Testing Decisions

- **What a good test is here:** exercise external behaviour through the module's public interface, not its internals. For `apply_batch` that means: given a doc + payload + timestamp, assert the returned doc's batch structure and status transitions - never reach into private helpers. For `inject_overlay`, assert properties of the returned HTML (markup present, placed before `</body>`, appended when absent) rather than exact string equality.
- **`apply_batch` (unit, Python `unittest`, zero deps).** Highest-value target. Cases: first save creates a pending batch; re-saving the same `sessionId` overwrites that batch rather than appending; a new `sessionId` appends; existing `reconciled` batches are never touched; `viewport` and `savedAt` are stamped; an empty/new doc is initialised correctly.
- **`inject_overlay` (unit, Python `unittest`).** Cases: Overlay markup and config are inserted immediately before the final `</body>`; the config carries the correct target name; markup is appended when no `</body>` exists; existing page content is otherwise unchanged.
- **One Playwright end-to-end test** of the full loop: boot the server against a sample page, load it, select an element, change a property and perform a resize/nudge, click Save, then assert the written `*.webtweak.json` contains a pending batch with the expected fingerprint and changes. This proves the whole loop and exercises `fingerprint`/`cssPath` indirectly.
- **Prior art:** stdlib `unittest` matches the existing Python CLI tooling pattern (leads tracker). The browser e2e needs the `playwright` pip package (`pip install playwright && playwright install chromium`); it is **not** satisfied by the Playwright MCP, which is a separate development-time tool. When the package is absent the e2e skips loudly (its reason shown via `pytest -ra`), and the browser loop is instead verified interactively via the MCP. The always-on coverage is the stdlib `unittest` + HTTP integration tests.
- **Not unit-tested in v1:** `fingerprint` and `cssPath` in isolation (covered by the e2e), and the HTTP handler/CLI glue (integration-level, low logic density).

## Out of Scope

- **Structural DOM reordering** ("move this section above that one") - requires rewriting hand-formatted source; deferred to v2.
- **Editing text copy** - copy changes are spoken to Claude, not done in the Overlay.
- **Per-breakpoint authoring / writing media queries** - v1 is single-viewport (base styles), with a viewport stamp so Claude can warn about mobile breakage; deliberate breakpoint editing is v2.
- **Borders, box-shadow, flex/grid alignment editors, hover/focus states, pseudo-elements** - excluded from the v1 property set.
- **Live-URL editing** - v1 operates on local source files only.
- **The reconcile step itself** - performed by Claude (future companion skill), not part of this codebase.
- **Pages requiring a build step** (Tailwind compile, server-side partials) may not render identically to production; acceptable since the target use is hand-coded editorial sites.

## Further Notes

- The whole design leans on the human-plus-Claude loop: because Claude reconciles, the editor can be "dumb" and only capture intent. This is the keystone decision (ADR-0001) and the reason a tool that would otherwise rival Pinegrow fits in a single Python file plus a browser overlay.
- A companion reconcile skill (read `*.webtweak.json`, locate elements by fingerprint, write clean CSS, flag ambiguous/systemic changes, mark batches reconciled, push) is the natural follow-up once v1 earns its keep.
- v2 candidates, in rough priority: structural reordering, per-breakpoint authoring, and a font-family dropdown populated from the site's actual `@font-face`/stack declarations.
