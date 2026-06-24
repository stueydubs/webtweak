import React from "react";
import { C, FONT_SERIF, FONT_UI, LAYOUT, Rect } from "../tokens";

const abs = (r: Rect): React.CSSProperties => ({
  position: "absolute",
  left: r.x,
  top: r.y,
  width: r.w,
  // height left to content; rects size the overlay boxes, not the text flow
});

export const SamplePage: React.FC<{
  titleColor: string;
  titleSize: number;
  titleRect?: Rect;
}> = ({ titleColor, titleSize, titleRect = LAYOUT.title }) => {
  return (
    <>
      <p
        style={{
          ...abs(LAYOUT.eyebrow),
          margin: 0,
          font: `600 15px/1 ${FONT_UI}`,
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          color: C.accent,
        }}
      >
        Field notes
      </p>

      <h1
        style={{
          ...abs(titleRect),
          margin: 0,
          fontFamily: FONT_SERIF,
          fontSize: titleSize,
          lineHeight: 1.1,
          fontWeight: 700,
          color: titleColor,
        }}
      >
        A page worth tweaking by eye
      </h1>

      <p
        style={{
          ...abs(LAYOUT.lede),
          margin: 0,
          fontFamily: FONT_SERIF,
          fontSize: 25,
          lineHeight: 1.45,
          color: C.lede,
        }}
      >
        A small editorial layout with enough variety — headings, body copy, a
        card, a button — to exercise the picker, the panel, resize and nudge.
      </p>

      <h2
        style={{
          ...abs(LAYOUT.sectionTitle),
          margin: 0,
          fontFamily: FONT_SERIF,
          fontSize: 32,
          fontWeight: 700,
          color: C.ink,
        }}
      >
        Precision instruments
      </h2>

      <p
        style={{
          ...abs(LAYOUT.para),
          margin: 0,
          fontFamily: FONT_SERIF,
          fontSize: 21,
          lineHeight: 1.6,
          color: C.ink,
        }}
      >
        Body copy sets the rhythm of an editorial page. Selecting this paragraph
        and adjusting its size, leading, or spacing is exactly the kind of
        by-eye change webtweak is built to capture.
      </p>

      {/* card */}
      <div
        style={{
          ...abs(LAYOUT.card),
          height: LAYOUT.card.h,
          background: "#fff",
          border: `1px solid ${C.cardBorder}`,
          borderRadius: 12,
        }}
      />
      <h3
        style={{
          ...abs(LAYOUT.cardH3),
          margin: 0,
          fontFamily: FONT_SERIF,
          fontSize: 23,
          fontWeight: 700,
          color: C.ink,
        }}
      >
        A card to resize
      </h3>
      <p
        style={{
          ...abs(LAYOUT.cardP),
          margin: 0,
          fontFamily: FONT_SERIF,
          fontSize: 19,
          lineHeight: 1.5,
          color: C.ink,
        }}
      >
        Drag the right or bottom edge of this card to resize it, or grab its
        interior to nudge it a few pixels. Both preview live.
      </p>
      <div
        style={{
          ...abs(LAYOUT.cta),
          height: LAYOUT.cta.h,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: C.ink,
          color: "#fff",
          borderRadius: 8,
          fontFamily: FONT_UI,
          fontSize: 17,
        }}
      >
        Primary action
      </div>

      <h2
        style={{
          ...abs(LAYOUT.sectionTitle2),
          margin: 0,
          fontFamily: FONT_SERIF,
          fontSize: 32,
          fontWeight: 700,
          color: C.ink,
        }}
      >
        Second section
      </h2>
    </>
  );
};
