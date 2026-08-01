import React from "react";
import { C, FONT_MONO, FONT_UI, VIEW, WIN } from "../tokens";

type FieldProps = {
  label: string;
  children: React.ReactNode;
  active?: boolean;
  edited?: boolean;   // shows the per-property revert mark, as the real panel does
  wide?: boolean;     // narrow label column, for the four-box spacing rows
};

const Field: React.FC<FieldProps> = ({ label, children, active, edited, wide }) => (
  <div
    style={{
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      marginBottom: 7,
      gap: 8,
    }}
  >
    {/* the revert × lives in the label column, where it cannot shift field widths */}
    <span
      style={{
        color: C.gold,
        fontSize: 15,
        lineHeight: 1,
        width: 12,
        visibility: edited ? "visible" : "hidden",
      }}
    >
      ×
    </span>
    <label style={{ color: C.muted, flex: `0 0 ${wide ? 62 : 80}px` }}>{label}</label>
    <div
      style={{
        flex: 1,
        minWidth: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "flex-end",
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

// the ▾ that opens a suggestion list (fonts, tracking presets, shadow presets)
const Chevron: React.FC = () => (
  <span
    style={{
      flex: "0 0 auto",
      background: C.field,
      border: `1px solid ${C.border}`,
      borderRadius: 5,
      color: C.muted,
      fontSize: 11,
      lineHeight: 1,
      padding: "6px 5px",
    }}
  >
    ▾
  </span>
);

// up/down arrows on a value you nudge by eye
const Stepper: React.FC = () => (
  <span style={{ flex: "0 0 auto", display: "flex", flexDirection: "column", gap: 2 }}>
    {["▲", "▼"].map((g) => (
      <span
        key={g}
        style={{
          background: C.field,
          border: `1px solid ${C.border}`,
          borderRadius: 4,
          color: C.muted,
          fontSize: 8,
          lineHeight: "10px",
          padding: "0 5px",
        }}
      >
        {g}
      </span>
    ))}
  </span>
);

const Legend: React.FC<{ children: React.ReactNode; collapsed?: boolean }> = ({
  children,
  collapsed,
}) => (
  <div
    style={{
      display: "flex",
      alignItems: "center",
      gap: 5,
      fontSize: 11,
      textTransform: "uppercase",
      letterSpacing: "0.08em",
      color: C.dim,
      marginBottom: 7,
    }}
  >
    {children}
    <span style={{ fontSize: 9, letterSpacing: 0 }}>{collapsed ? "▸" : "▾"}</span>
  </div>
);

const Swatch: React.FC<{ color: string }> = ({ color }) => (
  <span
    style={{
      flex: "0 0 auto",
      width: 38,
      height: 26,
      background: color,
      border: `1px solid ${C.border}`,
      borderRadius: 5,
      display: "inline-block",
    }}
  />
);

// a colour row: the swatch, plus the hex you can actually read and paste
const Colour: React.FC<{ color: string }> = ({ color }) => (
  <>
    <Swatch color={color} />
    <span style={{ ...inputBox, flex: "0 1 96px" }}>{color}</span>
  </>
);

// margin/padding: four sides on one row, plus the link toggle for "all round"
const Sides: React.FC<{ values: string[]; linked?: boolean }> = ({ values, linked }) => (
  <>
    {values.map((v, i) => (
      <span
        key={i}
        style={{
          flex: "1 1 0",
          minWidth: 0,
          background: C.field,
          border: `1px solid ${C.border}`,
          color: C.text,
          borderRadius: 4,
          padding: "5px 2px",
          fontSize: 12,
          fontFamily: FONT_MONO,
          textAlign: "center",
        }}
      >
        {v}
      </span>
    ))}
    <span
      style={{
        flex: "0 0 auto",
        background: linked ? "#23200f" : C.field,
        border: `1px solid ${linked ? C.gold : C.border}`,
        borderRadius: 4,
        color: linked ? C.gold : C.dim,
        fontSize: 11,
        lineHeight: 1,
        padding: "5px 4px",
      }}
    >
      🔗
    </span>
  </>
);

// overlay .wt-panel — properties panel. translateX drives the slide-in.
// Border is drawn collapsed: all five groups expanded would run past the window at
// this scale, and a folded group is worth showing anyway - it is how you keep a tall
// panel usable on a short screen.
export const Panel: React.FC<{
  translateX?: number;
  sizeValue: number;
  colorValue: string;
  active?: "size" | "color" | null;
  sizeEdited?: boolean;
  colorEdited?: boolean;
}> = ({
  translateX = 0,
  sizeValue,
  colorValue,
  active = null,
  sizeEdited,
  colorEdited,
}) => {
  const W = 330;
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
          <Chevron />
        </Field>
        <Field label="Size" active={active === "size"} edited={sizeEdited}>
          <span style={inputBox}>{Math.round(sizeValue)}px</span>
          <Stepper />
        </Field>
        <Field label="Weight">
          <span style={inputBox}>700</span>
        </Field>
        <Field label="Line">
          <span style={inputBox}>1.1</span>
          <Stepper />
        </Field>
        <Field label="Spacing">
          <span style={inputBox}>normal</span>
          <Chevron />
        </Field>
        {/* Four words in one row, sharing the narrow label column the spacing rows
            use. They read as words rather than L C R J because an abbreviation you
            have to decode is not a control - see overlay.css .wt-align. */}
        <Field label="Align" wide>
          <span style={{ display: "flex", flex: 1, gap: 3 }}>
            {["Left", "Centre", "Right", "Justify"].map((a) => (
              <span
                key={a}
                style={{
                  flex: "1 1 0",
                  minWidth: 0,
                  textAlign: "center",
                  background: a === "Left" ? C.gold : C.field,
                  color: a === "Left" ? C.goldInk : C.text,
                  border: `1px solid ${a === "Left" ? C.gold : C.border}`,
                  borderRadius: 5,
                  padding: "4px 1px",
                  fontSize: 11,
                  fontFamily: FONT_UI,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                }}
              >
                {a}
              </span>
            ))}
          </span>
        </Field>
      </div>

      <div style={{ marginBottom: 16 }}>
        <Legend>Colour</Legend>
        <Field label="Text" active={active === "color"} edited={colorEdited}>
          <Colour color={colorValue} />
        </Field>
        <Field label="Background">
          <Colour color="#faf8f4" />
        </Field>
      </div>

      <div style={{ marginBottom: 16 }}>
        <Legend>Box</Legend>
        <Field label="Width">
          <span style={inputBox}>940px</span>
          <Stepper />
        </Field>
        <Field label="Height">
          <span style={inputBox}>80px</span>
          <Stepper />
        </Field>
        <Field label="Margin" wide>
          <Sides values={["16px", "0px", "26px", "0px"]} />
        </Field>
        <Field label="Padding" wide>
          <Sides values={["0px", "0px", "0px", "0px"]} />
        </Field>
      </div>

      <div style={{ marginBottom: 14 }}>
        <Legend collapsed>Border</Legend>
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
