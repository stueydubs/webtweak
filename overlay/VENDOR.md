# Vendored third-party code

## `interact.min.js`

| | |
|---|---|
| Package | [`interact.js`](https://interactjs.io/) |
| Version | 1.10.27 |
| Upstream | https://github.com/taye/interact.js |
| Licence | MIT ([LICENSE](https://raw.github.com/taye/interact.js/main/LICENSE)) |
| Size | 95.9 KB |
| sha256 | `99b2bd3bd05261b0fdffdb811e6035a28d80b8b81e67cf9a228e77828f46c326` |

Provides the drag-nudge and edge-resize gestures in `overlay.js` (`attachInteract`).

**Why it is vendored rather than a dependency.** webtweak has no runtime dependencies
and no build step - `npx webtweak` has to work offline, against a page whose own network
may be unavailable, and the overlay is served from a three-entry allowlist in
`webtweak.js` (`OVERLAY_ASSETS`). A CDN `<script>` would fail exactly when someone is
editing a local page on a train. See CONTEXT.md.

**Why this file exists.** The banner above was the entire provenance record: no
checksum, no pinned artefact URL, no lockfile, and `git log` shows the file arriving
inside the initial squash commit, so history proves nothing either. That is 96 KB of
minified third-party code running in the same origin as the save endpoint, with nothing
to check it against. The hash above is that missing check - verify it before and after
any upgrade:

```sh
sha256sum overlay/interact.min.js
```

**On upgrading.** Fetch the release artefact from the upstream repo or npm, diff the
banner version, record the new hash here in the same commit, and re-run the browser
suite - `tests/test_e2e_browser.py` and `tests/test_e2e_shape_draw.py` are the ones that
actually exercise the gestures. `webtweak.js` also loads it with an `onerror` that sets
`window.__WEBTWEAK_INTERACT_ERR__`, and `overlay.js` surfaces that as a status message,
so a file that fails to parse degrades loudly rather than silently disabling drag.

**Known cosmetic issue.** The file ends with a `sourceMappingURL=interact.min.js.map`
comment for a map that is not shipped (`package.json` `files` covers `overlay/`, and the
map was never vendored). Devtools 404s on it once per load. Harmless, and left alone
rather than editing vendored bytes - editing them would invalidate the hash above, which
is the more valuable property.
