import { useState } from "react";
import { colors, mono } from "../theme";

interface Props {
  text: string;
  width?: number;
}

/** A small "i" affordance that reveals explanatory copy on hover/focus,
 * instead of that copy sitting on the page as a permanent paragraph. */
export default function InfoTooltip({ text, width = 220 }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <span
      style={{ position: "relative", display: "inline-flex" }}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      <span
        tabIndex={0}
        role="img"
        aria-label="More info"
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          width: 13,
          height: 13,
          borderRadius: "50%",
          border: `1px solid ${colors.textFaint}`,
          color: colors.textFaint,
          fontSize: 9,
          fontWeight: 700,
          lineHeight: 1,
          cursor: "help",
          flex: "none",
        }}
      >
        i
      </span>
      {open && (
        <span
          role="tooltip"
          style={{
            position: "absolute",
            bottom: "calc(100% + 6px)",
            left: 0,
            zIndex: 30,
            width,
            padding: "7px 9px",
            background: colors.text,
            color: colors.panelBg,
            borderRadius: 4,
            fontSize: 10.5,
            lineHeight: 1.45,
            fontWeight: 400,
            letterSpacing: "normal",
            ...mono,
            boxShadow: "0 4px 14px rgba(33,31,26,0.25)",
            pointerEvents: "none",
          }}
        >
          {text}
        </span>
      )}
    </span>
  );
}
