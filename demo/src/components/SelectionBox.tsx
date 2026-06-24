import React from "react";
import { C, FONT_MONO, Rect } from "../tokens";

// overlay .wt-box.wt-hover — blue outline that follows the cursor's element.
export const HoverBox: React.FC<{ rect: Rect; opacity?: number }> = ({
  rect,
  opacity = 1,
}) => (
  <div
    style={{
      position: "absolute",
      left: rect.x,
      top: rect.y,
      width: rect.w,
      height: rect.h,
      border: `1px solid ${C.hover}`,
      background: C.hoverFill,
      opacity,
      pointerEvents: "none",
    }}
  />
);

// overlay .wt-box.wt-selected — gold outline + monospace tag + resize grips.
export const SelectionBox: React.FC<{
  rect: Rect;
  tag?: string;
  grips?: boolean;
  opacity?: number;
}> = ({ rect, tag, grips = true, opacity = 1 }) => {
  const grip: React.CSSProperties = {
    position: "absolute",
    width: 9,
    height: 9,
    background: C.gold,
    border: `1px solid ${C.goldInk}`,
    borderRadius: 2,
  };
  return (
    <div
      style={{
        position: "absolute",
        left: rect.x,
        top: rect.y,
        width: rect.w,
        height: rect.h,
        border: `1px solid ${C.gold}`,
        background: C.selFill,
        opacity,
        pointerEvents: "none",
      }}
    >
      {tag && (
        <span
          style={{
            position: "absolute",
            top: -21,
            left: -1,
            background: C.gold,
            color: C.goldInk,
            font: `600 12px/1.4 ${FONT_MONO}`,
            padding: "1px 7px",
            borderRadius: "3px 3px 0 0",
            whiteSpace: "nowrap",
          }}
        >
          {tag}
        </span>
      )}
      {grips && (
        <>
          <span style={{ ...grip, right: -5, top: "calc(50% - 4px)" }} />
          <span style={{ ...grip, bottom: -5, left: "calc(50% - 4px)" }} />
          <span style={{ ...grip, right: -5, bottom: -5 }} />
        </>
      )}
    </div>
  );
};
