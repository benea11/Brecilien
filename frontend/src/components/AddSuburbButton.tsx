import { useEffect, useRef, useState } from "react";
import { colors, mono } from "../theme";
import type { GeocodeResult } from "../types";
import LocationMultiSearch from "./LocationMultiSearch";

interface Props {
  buttonStyle: React.CSSProperties;
  onAdd: (locations: GeocodeResult[]) => void;
}

/** Sits in the Sidebar's TOPOLOGY row next to "+ NODE" / "IMPORT CSV" --
 * lets the user search one or more suburbs and pull their MV substations
 * into the *current* project, the same multi-pick flow ProjectMenu uses for
 * a brand-new project. */
export default function AddSuburbButton({ buttonStyle, onAdd }: Props) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<GeocodeResult[]>([]);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  function submit() {
    if (selected.length === 0) return;
    onAdd(selected);
    setSelected([]);
    setOpen(false);
  }

  return (
    <div ref={rootRef} style={{ position: "relative" }}>
      <button style={buttonStyle} onClick={() => setOpen((o) => !o)}>
        + SUBURB
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            left: 0,
            zIndex: 20,
            width: 300,
            padding: 10,
            background: colors.panelBg,
            border: `1px solid ${colors.border}`,
            borderRadius: 6,
            boxShadow: "0 4px 14px rgba(33,31,26,0.18)",
          }}
        >
          <div style={{ ...mono, fontSize: 9.5, letterSpacing: "0.08em", color: colors.textFaint, marginBottom: 6 }}>
            ADD SUBURBS + MV SUBSTATIONS
          </div>
          <LocationMultiSearch selected={selected} onChange={setSelected} autoFocus />
          {selected.length > 0 && (
            <button
              onClick={submit}
              style={{
                width: "100%",
                height: 28,
                marginTop: 8,
                border: "none",
                borderRadius: 4,
                background: colors.teal,
                color: colors.panelBg,
                cursor: "pointer",
                ...mono,
                fontSize: 11,
                fontWeight: 600,
                letterSpacing: "0.05em",
              }}
            >
              ADD TO PROJECT
            </button>
          )}
        </div>
      )}
    </div>
  );
}
