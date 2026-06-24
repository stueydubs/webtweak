# webtweak demo (Remotion)

Programmatic [Remotion](https://remotion.dev) source for the landing-page demo
video. It recreates the webtweak overlay in React/CSS (tokens lifted verbatim
from `overlay/overlay.css`) and animates the full loop — load, select, nudge,
resize, restyle, save, reconcile — so the demo is crisp and repeatable with no
flaky screen capture.

One composition: **`WebtweakDemo`**, 1920×1080, 30fps, 660 frames (~22s).

## Develop

```bash
npm install
npm run studio        # interactive Remotion Studio at localhost:3000
```

## Render

Outputs are written straight into `../site/` (committed; the GitHub Pages
deploy serves them as static files, so CI never runs a headless render).

```bash
npm run render        # ../site/demo.mp4   (h264)
npm run poster        # ../site/demo-poster.png  (frame 330, mid-restyle)
npm run og            # ../site/og.png      (frame 636, outro card — 1200x630-ish)
```

Or directly:

```bash
npx remotion render WebtweakDemo ../site/demo.mp4 --codec=h264
npx remotion still  WebtweakDemo ../site/demo-poster.png --frame=330
```

## Layout

- `src/tokens.ts` — colour tokens + the shared canvas geometry/layout. The
  sample page and the overlay boxes read the same rects, so selection, grips,
  and hover line up exactly without any DOM measurement.
- `src/sample/SamplePage.tsx` — the fake editorial page being edited.
- `src/components/` — `FakeBrowser`, `TopBar`, `Panel`, `SelectionBox`,
  `Cursor`, `CodePane`.
- `src/WebtweakDemo.tsx` — the timeline: cursor path, beat timing, the captured
  `page.webtweak.json` snippet, and the reconciled CSS.

`node_modules/` and Remotion's `out/` are gitignored; only the rendered media in
`../site/` is committed.
