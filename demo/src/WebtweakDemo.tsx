import React from "react";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  useCurrentFrame,
} from "remotion";
import { C, FONT_MONO, FONT_UI, LAYOUT, Rect } from "./tokens";
import { FakeBrowser } from "./components/FakeBrowser";
import { TopBar, Crumb } from "./components/TopBar";
import { HoverBox, SelectionBox } from "./components/SelectionBox";
import { Panel } from "./components/Panel";
import { Cursor } from "./components/Cursor";
import { CodePane, Line, Tok } from "./components/CodePane";
import { SamplePage } from "./sample/SamplePage";

// ---- helpers --------------------------------------------------------------
const clampOpts = {
  extrapolateLeft: "clamp",
  extrapolateRight: "clamp",
} as const;

const ip = (frame: number, inp: number[], out: number[], ease = false) =>
  interpolate(frame, inp, out, {
    ...clampOpts,
    ...(ease ? { easing: Easing.inOut(Easing.ease) } : {}),
  });

function hexToRgb(h: string) {
  const n = parseInt(h.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function lerpHex(a: string, b: string, t: number) {
  const ra = hexToRgb(a),
    rb = hexToRgb(b);
  const m = ra.map((v, i) => Math.round(v + (rb[i] - v) * t));
  return "#" + m.map((v) => v.toString(16).padStart(2, "0")).join("");
}

// cursor path: linear interpolation across hand-set waypoints
const CX = [
  [0, 1520, 840],
  [95, 1520, 840],
  [130, 960, 312],
  [146, 960, 312],
  [178, 960, 312],
  [212, 960, 330],
  [228, 960, 330],
  [248, 1400, 330],
  [272, 1462, 338],
  [300, 1600, 360],
  [336, 1600, 360],
  [375, 1666, 262],
  [414, 1666, 262],
  [446, 1762, 130],
  [466, 1762, 130],
  [512, 1762, 130],
] as const;
const CXF = CX.map((p) => p[0]);

// ---- code-pane colourisers -----------------------------------------------
function tokJSON(line: string): Tok[] {
  const re = /("(?:[^"\\]|\\.)*")|(-?\d+(?:\.\d+)?)|([{}\[\],:])|(\s+)|(\S+)/g;
  const raw: { v: string; kind: string }[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(line))) {
    if (m[1]) raw.push({ v: m[1], kind: "str" });
    else if (m[2]) raw.push({ v: m[2], kind: "num" });
    else if (m[3]) raw.push({ v: m[3], kind: "punc" });
    else if (m[4]) raw.push({ v: m[4], kind: "ws" });
    else raw.push({ v: m[5], kind: "id" });
  }
  return raw.map((t, i) => {
    if (t.kind === "str") {
      // key if the next non-space token is a colon
      let j = i + 1;
      while (j < raw.length && raw[j].kind === "ws") j++;
      const isKey = raw[j]?.v === ":";
      return { t: t.v, c: isKey ? C.gold : C.green };
    }
    if (t.kind === "num") return { t: t.v, c: "#6ea8fe" };
    if (t.kind === "punc") return { t: t.v, c: C.dim };
    return { t: t.v, c: C.muted };
  });
}

function tokCSS(line: string): Tok[] {
  if (line.includes("{")) {
    const sel = line.replace("{", "").trim();
    return [
      { t: sel + " ", c: C.gold },
      { t: "{", c: C.dim },
    ];
  }
  if (line.trim() === "}") return [{ t: "}", c: C.dim }];
  const m = line.match(/^(\s*)([\w-]+)(:\s*)(.+?)(;?)$/);
  if (!m) return [{ t: line, c: C.text }];
  return [
    { t: m[1], c: C.text },
    { t: m[2], c: "#6ea8fe" },
    { t: m[3], c: C.dim },
    { t: m[4], c: C.green },
    { t: m[5], c: C.dim },
  ];
}

const JSON_LINES = [
  `{ "target": "page.html",`,
  `  "batches": [{`,
  `    "status": "pending", "viewport": 1728,`,
  `    "patches": [{`,
  `      "fingerprint": {`,
  `        "tag": "h1", "classes": ["title"] },`,
  `      "changes": {`,
  `        "width": "940px", "color": "#7a5c3e",`,
  `        "font-size": "64px",`,
  `        "nudge": { "dx": 0, "dy": 16 } }`,
  `    }] }]`,
  `}`,
].map((l): Line => ({ toks: tokJSON(l) }));

const CSS_LINES = [
  `h1.title {`,
  `  width: 940px;`,
  `  margin-top: 16px;`,
  `  color: #7a5c3e;`,
  `  font-size: 64px;`,
  `}`,
].map((l): Line => ({ toks: tokCSS(l) }));

// ---- composition ----------------------------------------------------------
export const WebtweakDemo: React.FC = () => {
  const f = useCurrentFrame();

  // scene fades
  const browserOp = ip(f, [0, 22], [0, 1]);
  const pageOp = ip(f, [12, 40], [0, 1]);
  const barDrop = ip(f, [40, 70], [-56, 0], true);
  const barOp = ip(f, [40, 64], [0, 1]);

  // selection / nudge / resize
  const selected = f >= 144;
  const dy = ip(f, [178, 212], [0, 16]);
  const w = ip(f, [248, 272], [880, 940]);
  const titleRect: Rect = {
    x: LAYOUT.title.x,
    y: LAYOUT.title.y + dy,
    w,
    h: LAYOUT.title.h,
  };

  // restyle
  const colorT = ip(f, [335, 372], [0, 1]);
  const titleColor = lerpHex(C.ink, C.accent, colorT);
  const titleSize = ip(f, [378, 416], [56, 64]);
  const panelActive: "size" | "color" | null =
    f >= 335 && f < 374 ? "color" : f >= 378 && f < 418 ? "size" : null;

  // panel
  const panelMounted = f >= 268;
  const panelX = ip(f, [272, 300], [380, 0], true);
  const panelOp = ip(f, [524, 546], [1, 0]);

  // save
  const saveActive = f >= 460 && f < 474;
  const status = f >= 470 ? "Saved ✓" : "";

  // hover (pre-select)
  const hoverOp = ip(f, [116, 130], [0, 1]) * ip(f, [140, 146], [1, 0]);
  const selOp = ip(f, [144, 152], [0, 1]) * ip(f, [524, 544], [1, 0]);

  // cursor
  const cx = interpolate(
    f,
    CXF as unknown as number[],
    CX.map((p) => p[1]),
    clampOpts
  );
  const cy = interpolate(
    f,
    CXF as unknown as number[],
    CX.map((p) => p[2]),
    clampOpts
  );
  const cursorOp = ip(f, [78, 92], [0, 1]) * ip(f, [520, 540], [1, 0]);
  const pressed = (f >= 140 && f < 150) || saveActive;

  // save snippet + reconcile
  const jsonMounted = f >= 470;
  const jsonY = ip(f, [470, 502], [180, 0], true);
  const jsonOp = ip(f, [470, 494], [0, 1]);
  const jsonLines = Math.floor(ip(f, [486, 540], [0, JSON_LINES.length]));

  const captionOp = ip(f, [520, 538], [0, 1]) * ip(f, [600, 616], [1, 0]);
  const cssMounted = f >= 540;
  const cssLines = Math.floor(ip(f, [546, 598], [0, CSS_LINES.length]));

  // outro
  const outroOp = ip(f, [606, 630], [0, 1]);
  const outroInner = ip(f, [616, 642], [0, 1]);
  const outroRise = ip(f, [616, 648], [24, 0], true);

  const crumb =
    f >= 146 ? <Crumb chain={["main.wrap", "h1.title"]} /> : undefined;

  return (
    <AbsoluteFill
      style={{
        background:
          "radial-gradient(120% 120% at 50% 0%, #14171d 0%, #0b0d10 55%, #07080a 100%)",
        fontFamily: FONT_UI,
      }}
    >
      {/* browser chrome */}
      <AbsoluteFill style={{ opacity: browserOp }}>
        <FakeBrowser />
      </AbsoluteFill>

      {/* page content */}
      <AbsoluteFill style={{ opacity: pageOp }}>
        <SamplePage
          titleColor={titleColor}
          titleSize={titleSize}
          titleRect={titleRect}
        />
      </AbsoluteFill>

      {/* webtweak top bar */}
      <AbsoluteFill style={{ opacity: barOp }}>
        <div style={{ transform: `translateY(${barDrop}px)` }}>
          <TopBar crumb={crumb} status={status} saveActive={saveActive} />
        </div>
      </AbsoluteFill>

      {/* overlay boxes */}
      {hoverOp > 0.01 && <HoverBox rect={LAYOUT.title} opacity={hoverOp} />}
      {selected && (
        <SelectionBox rect={titleRect} tag="h1.title" opacity={selOp} />
      )}

      {/* properties panel */}
      {panelMounted && (
        <div style={{ opacity: panelOp }}>
          <Panel
            translateX={panelX}
            sizeValue={titleSize}
            colorValue={lerpHex(C.ink, C.accent, colorT)}
            active={panelActive}
          />
        </div>
      )}

      {/* save snippet: captured intent */}
      {jsonMounted && (
        <div style={{ opacity: jsonOp, transform: `translateY(${jsonY}px)` }}>
          <CodePane
            title="page.webtweak.json"
            lines={JSON_LINES}
            visibleLines={jsonLines}
            x={132}
            y={560}
            width={760}
            caret={f < 545}
          />
        </div>
      )}

      {/* reconcile */}
      {f >= 518 && (
        <div
          style={{
            position: "absolute",
            top: 486,
            left: 0,
            width: "100%",
            textAlign: "center",
            opacity: captionOp,
          }}
        >
          <span
            style={{
              display: "inline-block",
              background: "rgba(15,17,21,0.92)",
              border: `1px solid ${C.border}`,
              borderRadius: 999,
              padding: "12px 26px",
              color: C.text,
              fontSize: 25,
              boxShadow: "0 10px 30px rgba(0,0,0,0.45)",
            }}
          >
            Tell Claude:{" "}
            <span
              style={{
                color: C.gold,
                fontFamily: FONT_MONO,
                fontStyle: "italic",
              }}
            >
              reconcile page.html
            </span>
          </span>
        </div>
      )}
      {cssMounted && (
        <div style={{ opacity: ip(f, [540, 560], [0, 1]) }}>
          <CodePane
            title="styles.css"
            lines={CSS_LINES}
            visibleLines={cssLines}
            x={1028}
            y={604}
            width={760}
            caret={f < 600}
          />
        </div>
      )}

      {/* cursor */}
      {cursorOp > 0.01 && (
        <div style={{ opacity: cursorOp }}>
          <Cursor x={cx} y={cy} pressed={pressed} />
        </div>
      )}

      {/* outro */}
      {f >= 604 && (
        <AbsoluteFill
          style={{
            opacity: outroOp,
            background:
              "radial-gradient(120% 120% at 50% 40%, #14171d 0%, #0b0d10 60%, #07080a 100%)",
            justifyContent: "center",
            alignItems: "center",
          }}
        >
          <div
            style={{
              opacity: outroInner,
              transform: `translateY(${outroRise}px)`,
              textAlign: "center",
            }}
          >
            <div
              style={{
                fontSize: 84,
                fontWeight: 700,
                letterSpacing: "0.01em",
                color: C.gold,
              }}
            >
              webtweak
            </div>
            <div
              style={{
                fontSize: 32,
                color: C.text,
                marginTop: 14,
              }}
            >
              Edit by eye. Claude writes the CSS.
            </div>
            <div
              style={{
                marginTop: 40,
                display: "inline-block",
                background: C.field,
                border: `1px solid ${C.border}`,
                borderRadius: 10,
                padding: "14px 26px",
                fontFamily: FONT_MONO,
                fontSize: 26,
                color: C.muted,
              }}
            >
              <span style={{ color: C.dim }}>$ </span>npx webtweak page.html
            </div>
          </div>
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};
