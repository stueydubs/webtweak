import React from "react";
import { C, FONT_MONO } from "../tokens";

export type Tok = { t: string; c?: string };
export type Line = { indent?: number; toks: Tok[] };

// A small editor pane: filename tab + monospace body. Lines reveal one at a
// time (driven by `visibleLines`) with a caret on the writing line, so it
// reads as code being typed without mid-token slicing artefacts.
export const CodePane: React.FC<{
  title: string;
  lines: Line[];
  visibleLines: number;
  x: number;
  y: number;
  width: number;
  caret?: boolean;
}> = ({ title, lines, visibleLines, x, y, width, caret = true }) => {
  const shown = Math.max(0, Math.min(visibleLines, lines.length));
  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        width,
        background: C.field,
        border: `1px solid ${C.border}`,
        borderRadius: 12,
        boxShadow: "0 24px 70px rgba(0,0,0,0.5)",
        overflow: "hidden",
        fontFamily: FONT_MONO,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "10px 16px",
          background: C.panel,
          borderBottom: `1px solid ${C.border}`,
          fontSize: 14,
          color: C.muted,
        }}
      >
        <span
          style={{
            width: 9,
            height: 9,
            borderRadius: "50%",
            background: C.gold,
            display: "inline-block",
          }}
        />
        {title}
      </div>
      <div style={{ padding: "16px 20px", fontSize: 18, lineHeight: 1.65 }}>
        {lines.slice(0, shown).map((ln, i) => {
          const writing = i === shown - 1;
          return (
            <div
              key={i}
              style={{ paddingLeft: (ln.indent ?? 0) * 22, whiteSpace: "pre" }}
            >
              {ln.toks.map((tk, j) => (
                <span key={j} style={{ color: tk.c ?? C.text }}>
                  {tk.t}
                </span>
              ))}
              {caret && writing && (
                <span style={{ color: C.gold, marginLeft: 1 }}>▍</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
