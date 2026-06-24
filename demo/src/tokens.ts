// Visual identity — lifted verbatim from overlay/overlay.css so the demo's
// recreated UI matches the real tool pixel-for-pixel.
export const C = {
  // webtweak overlay chrome
  topBar: "#15171c",
  panel: "#1a1d23",
  field: "#0f1115",
  gold: "#ffd479",
  goldHover: "#ffdd94",
  goldInk: "#1a1300",
  hover: "rgba(110, 168, 254, 0.9)",
  hoverFill: "rgba(110, 168, 254, 0.08)",
  selFill: "rgba(255, 212, 121, 0.06)",
  green: "#8ad18a",
  text: "#e8eaed",
  muted: "#aab0bb",
  dim: "#717784",
  border: "#2c303a",
  btn: "#23262e",
  btnBorder: "#3a3f4b",
  // the editorial sample page
  ink: "#1a1a1a",
  paper: "#faf8f4",
  accent: "#7a5c3e",
  lede: "#44403a",
  cardBorder: "#e7e1d8",
} as const;

export const FONT_UI =
  '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
export const FONT_MONO = "ui-monospace, SFMono-Regular, Menlo, monospace";
export const FONT_SERIF = 'Georgia, "Times New Roman", serif';

// ---- canvas geometry (1920x1080) -----------------------------------------
export const CANVAS = { w: 1920, h: 1080 };

// Fake browser window card
export const WIN = { x: 96, y: 56, w: 1728, h: 968 };
export const TITLEBAR = 52; // browser chrome (traffic lights + url)
export const WT_BAR_H = 44; // webtweak dark top bar

export const VIEW = {
  x: WIN.x,
  y: WIN.y + TITLEBAR,
  w: WIN.w,
  h: WIN.h - TITLEBAR,
};
export const PAGE_TOP = VIEW.y + WT_BAR_H; // top of the actual page content

// Editorial content column, centred in the window
const COL_W = 880;
const COL_X = WIN.x + (WIN.w - COL_W) / 2; // centred

export type Rect = { x: number; y: number; w: number; h: number };

// Hand-authored absolute layout: the SamplePage positions each element at
// these rects, and the overlay boxes draw at the very same rects — so hover /
// selection / grips line up exactly without any DOM measurement.
function build() {
  const x = COL_X;
  const w = COL_W;
  let y = PAGE_TOP + 60;
  const el = (h: number, gapAfter: number): Rect => {
    const r = { x, y, w, h };
    y += h + gapAfter;
    return r;
  };
  const eyebrow = el(20, 18);
  const title = el(80, 30); // the big headline (single line, hugs the text)
  const lede = el(76, 40);
  const sectionTitle = el(40, 16);
  const para = el(96, 28);
  // the card is a touch narrower visual block
  const cardY = y;
  const card = { x, y: cardY, w, h: 196 };
  const cardH3 = { x: x + 28, y: cardY + 24, w: w - 56, h: 30 };
  const cardP = { x: x + 28, y: cardY + 66, w: w - 56, h: 60 };
  const cta = { x: x + 28, y: cardY + 138, w: 190, h: 48 };
  y += card.h + 30;
  const sectionTitle2 = el(40, 16);
  return {
    eyebrow,
    title,
    lede,
    sectionTitle,
    para,
    card,
    cardH3,
    cardP,
    cta,
    sectionTitle2,
  };
}

export const LAYOUT = build();
