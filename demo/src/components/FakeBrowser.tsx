import React from "react";
import { C, FONT_MONO, TITLEBAR, WIN } from "../tokens";

// The browser window card: rounded chrome with traffic lights + an address
// bar, and a paper-coloured viewport body. Page content and the webtweak
// overlay are drawn as separate canvas-absolute layers on top (everything in
// this demo lives in one shared canvas coordinate space — see tokens.LAYOUT).
export const FakeBrowser: React.FC = () => {
  return (
    <div
      style={{
        position: "absolute",
        left: WIN.x,
        top: WIN.y,
        width: WIN.w,
        height: WIN.h,
        borderRadius: 14,
        background: C.paper,
        boxShadow: "0 40px 120px rgba(0,0,0,0.55)",
        overflow: "hidden",
        border: "1px solid rgba(255,255,255,0.06)",
      }}
    >
      {/* titlebar */}
      <div
        style={{
          height: TITLEBAR,
          background: C.btn,
          display: "flex",
          alignItems: "center",
          gap: 16,
          padding: "0 18px",
          borderBottom: `1px solid ${C.border}`,
        }}
      >
        <div style={{ display: "flex", gap: 9 }}>
          {["#ff5f57", "#febc2e", "#28c840"].map((col) => (
            <span
              key={col}
              style={{
                width: 13,
                height: 13,
                borderRadius: "50%",
                background: col,
              }}
            />
          ))}
        </div>
        <div
          style={{
            flex: 1,
            maxWidth: 520,
            height: 30,
            background: C.field,
            borderRadius: 8,
            border: `1px solid ${C.border}`,
            display: "flex",
            alignItems: "center",
            padding: "0 14px",
            color: C.muted,
            fontFamily: FONT_MONO,
            fontSize: 13,
          }}
        >
          localhost:8723/page.html
        </div>
      </div>
    </div>
  );
};
