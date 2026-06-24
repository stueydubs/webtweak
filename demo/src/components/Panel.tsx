import React from "react";
import { C, FONT_MONO, FONT_UI, VIEW, WIN } from "../tokens";

type FieldProps = {
  label: string;
  children: React.ReactNode;
  active?: boolean;
};

const Field: React.FC<FieldProps> = ({ label, children, active }) => (
  <div
    style={{
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      marginBottom: 7,
      gap: 8,
    }}
  >
    <label style={{ color: C.muted, flex: "0 0 92px" }}>{label}</label>
    <div
      style={{
        flex: 1,
        minWidth: 0,
        display: "flex",
        alignItems: "center",
        gap: 6,
        ...(active
          ? { outline: `2px solid ${C.gold}`, outlineOffset: 2, borderRadius: 6 }
          : {}),
      }}
    >
      {children}
    </div>
  </div>
);

const inputBox: React.CSSProperties = {
  flex: 1,
  minWidth: 0,
  background: C.field,
  border: `1px solid ${C.border}`,
  color: C.text,
  borderRadius: 5,
  padding: "5px 8px",
  fontSize: 14,
  fontFamily: FONT_MONO,
};

const Legend: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div
    style={{
      fontSize: 11,
      textTransform: "uppercase",
      letterSpacing: "0.08em",
      color: C.dim,
      marginBottom: 7,
    }}
  >
    {children}
  </div>
);

const Swatch: React.FC<{ color: string }> = ({ color }) => (
  <span
    style={{
      width: 40,
      height: 26,
      background: color,
      border: `1px solid ${C.border}`,
      borderRadius: 5,
      display: "inline-block",
    }}
  />
);

// overlay .wt-panel — properties panel. translateX drives the slide-in.
export const Panel: React.FC<{
  translateX?: number;
  sizeValue: number;
  colorValue: string;
  active?: "size" | "color" | null;
}> = ({ translateX = 0, sizeValue, colorValue, active = null }) => {
  const W = 320;
  return (
    <div
      style={{
        position: "absolute",
        top: VIEW.y + 56,
        left: WIN.x + WIN.w - 28 - W,
        width: W,
        background: C.panel,
        color: C.text,
        border: `1px solid ${C.border}`,
        borderRadius: 12,
        padding: "14px 16px 18px",
        boxShadow: "0 8px 30px rgba(0,0,0,0.45)",
        fontFamily: FONT_UI,
        fontSize: 14,
        transform: `translateX(${translateX}px)`,
      }}
    >
      <h3
        style={{
          margin: "2px 0 12px",
          fontSize: 13,
          fontWeight: 700,
          color: C.gold,
          textTransform: "uppercase",
          letterSpacing: "0.06em",
        }}
      >
        Properties
      </h3>

      <div style={{ marginBottom: 16 }}>
        <Legend>Type</Legend>
        <Field label="Font">
          <span style={inputBox}>Georgia, serif</span>
        </Field>
        <Field label="Size" active={active === "size"}>
          <span style={inputBox}>{Math.round(sizeValue)}</span>
          <span style={{ color: C.dim }}>px</span>
        </Field>
        <Field label="Weight">
          <span style={inputBox}>700</span>
        </Field>
        <Field label="Line">
          <span style={inputBox}>1.1</span>
        </Field>
      </div>

      <div style={{ marginBottom: 16 }}>
        <Legend>Colour</Legend>
        <Field label="Text" active={active === "color"}>
          <Swatch color={colorValue} />
          <span style={{ ...inputBox, flex: "none", width: 96 }}>
            {colorValue}
          </span>
        </Field>
        <Field label="Background">
          <Swatch color="#faf8f4" />
        </Field>
      </div>

      <div style={{ marginBottom: 14 }}>
        <Legend>Box</Legend>
        <Field label="Width">
          <span style={inputBox}>880</span>
          <span style={{ color: C.dim }}>px</span>
        </Field>
        <Field label="Margin">
          <span style={inputBox}>0 0 26px</span>
        </Field>
      </div>

      <button
        style={{
          width: "100%",
          border: `1px solid ${C.btnBorder}`,
          background: C.btn,
          color: C.text,
          padding: "8px 0",
          borderRadius: 6,
          fontSize: 14,
          fontFamily: FONT_UI,
        }}
      >
        Reset this element
      </button>
      <p
        style={{
          color: C.dim,
          fontSize: 12,
          lineHeight: 1.5,
          margin: "10px 0 0",
        }}
      >
        Changes preview live and are captured as intent. Claude reconciles them
        into clean CSS on save.
      </p>
    </div>
  );
};
