import React from "react";

// A crisp arrow cursor drawn in SVG so it scales without blur. The tip is at
// the component's (x, y); `pressed` gives a subtle click dip.
export const Cursor: React.FC<{
  x: number;
  y: number;
  pressed?: boolean;
}> = ({ x, y, pressed = false }) => {
  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        transform: `scale(${pressed ? 0.88 : 1})`,
        transformOrigin: "top left",
        filter: "drop-shadow(0 2px 3px rgba(0,0,0,0.45))",
        pointerEvents: "none",
      }}
    >
      <svg width="34" height="34" viewBox="0 0 24 24" fill="none">
        <path
          d="M5.5 3.5 L5.5 19 L9.4 15.3 L12.1 21.4 L14.6 20.3 L11.9 14.2 L17 14.1 Z"
          fill="#fff"
          stroke="#15171c"
          strokeWidth="1.4"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
};
