import React from "react";
import { C, FONT_MONO, FONT_UI, VIEW, WT_BAR_H } from "../tokens";

// Recreation of overlay's .wt-bar — the dark top bar with gold logo,
// monospace breadcrumb, status, and the Deselect / Save buttons.
export const TopBar: React.FC<{
  crumb?: React.ReactNode;
  status?: string;
  saveActive?: boolean; // cursor pressing Save
  hasEdits?: boolean;   // lights Undo, as the real bar does
}> = ({ crumb, status, saveActive, hasEdits }) => {
  return (
    <div
      style={{
        position: "absolute",
        left: VIEW.x,
        top: VIEW.y,
        width: VIEW.w,
        height: WT_BAR_H,
        display: "flex",
        alignItems: "center",
        gap: 14,
        padding: "0 16px",
        background: C.topBar,
        color: C.text,
        fontFamily: FONT_UI,
        fontSize: 14,
        boxShadow:
          "0 1px 0 rgba(255,255,255,0.06), 0 2px 12px rgba(0,0,0,0.4)",
      }}
    >
      <span style={{ fontWeight: 700, letterSpacing: "0.02em", color: C.gold }}>
        webtweak
      </span>
      <span
        style={{
          flex: 1,
          minWidth: 0,
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
          color: C.muted,
          fontFamily: FONT_MONO,
          fontSize: 13,
        }}
      >
        {crumb ?? "click an element to select"}
      </span>
      <span
        style={{
          color: C.green,
          fontSize: 13,
          minWidth: 96,
          textAlign: "right",
        }}
      >
        {status ?? ""}
      </span>
      {/* Undo / Redo, dimming when their stack is empty - the only place history is
          visible in the real bar, so the demo would look a version behind without it.
          Redo is dim here because nothing has been undone yet. */}
      {[
        { label: "Undo", spent: !hasEdits },
        { label: "Redo", spent: true },
      ].map(({ label, spent }) => (
        <button
          key={label}
          style={{
            border: `1px solid ${C.btnBorder}`,
            background: C.btn,
            color: C.text,
            padding: "7px 13px",
            borderRadius: 6,
            fontSize: 14,
            fontFamily: FONT_UI,
            opacity: spent ? 0.35 : 1,
          }}
        >
          {label}
        </button>
      ))}
      <button
        style={{
          border: `1px solid ${C.btnBorder}`,
          background: C.btn,
          color: C.text,
          padding: "7px 15px",
          borderRadius: 6,
          fontSize: 14,
          fontFamily: FONT_UI,
        }}
      >
        Deselect
      </button>
      <button
        style={{
          border: `1px solid ${C.gold}`,
          background: saveActive ? C.goldHover : C.gold,
          color: C.goldInk,
          padding: "7px 16px",
          borderRadius: 6,
          fontSize: 14,
          fontWeight: 600,
          fontFamily: FONT_UI,
          transform: saveActive ? "translateY(1px)" : "none",
        }}
      >
        Save
      </button>
    </div>
  );
};

// Breadcrumb content matching overlay's crumb style: muted chain with the
// selected node in bright text.
export const Crumb: React.FC<{ chain: string[]; activeLast?: boolean }> = ({
  chain,
  activeLast = true,
}) => (
  <>
    {chain.map((node, i) => {
      const last = i === chain.length - 1;
      return (
        <React.Fragment key={i}>
          <span style={{ color: last && activeLast ? C.text : C.muted }}>
            {node}
          </span>
          {!last && <span style={{ color: C.dim }}> {" › "} </span>}
        </React.Fragment>
      );
    })}
  </>
);
