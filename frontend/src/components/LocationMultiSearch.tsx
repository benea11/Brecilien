import { useEffect, useRef, useState } from "react";
import { geocode } from "../api";
import { colors, mono } from "../theme";
import type { GeocodeResult } from "../types";

const SEARCH_DEBOUNCE_MS = 400;

export function shortName(r: GeocodeResult): string {
  return r.display_name.split(",")[0];
}

interface Props {
  selected: GeocodeResult[];
  onChange: (locations: GeocodeResult[]) => void;
  placeholder?: string;
  autoFocus?: boolean;
}

/** Debounced Nominatim search + an "add to a pending list" picker, shared by
 * the new-project flow (ProjectMenu) and the add-suburbs-to-current-project
 * flow (AddSuburbButton) -- both need the identical search/select/remove
 * interaction, just with a different action once the list is ready. */
export default function LocationMultiSearch({ selected, onChange, placeholder, autoFocus }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<GeocodeResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const debounceRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    window.clearTimeout(debounceRef.current);
    if (!query.trim()) {
      setResults([]);
      setSearchError(null);
      return;
    }
    setSearching(true);
    debounceRef.current = window.setTimeout(() => {
      geocode(query)
        .then((r) => {
          setResults(r);
          setSearchError(null);
        })
        .catch((e) => setSearchError(String(e)))
        .finally(() => setSearching(false));
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(debounceRef.current);
  }, [query]);

  function add(r: GeocodeResult) {
    if (!selected.some((l) => l.lat === r.lat && l.lon === r.lon)) {
      onChange([...selected, r]);
    }
    setQuery("");
    setResults([]);
  }

  function remove(i: number) {
    onChange(selected.filter((_, idx) => idx !== i));
  }

  return (
    <div>
      <input
        autoFocus={autoFocus}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={placeholder ?? "e.g. Lyon, France"}
        style={{
          width: "100%",
          height: 29,
          border: `1px solid ${colors.border}`,
          borderRadius: 4,
          background: colors.bg,
          ...mono,
          fontSize: 11,
          color: colors.text,
          padding: "0 8px",
        }}
      />
      {searching && <div style={{ ...mono, fontSize: 10, color: colors.textFaint, marginTop: 6 }}>Searching…</div>}
      {searchError && <div style={{ ...mono, fontSize: 10, color: colors.red, marginTop: 6 }}>{searchError}</div>}
      {results.length > 0 && (
        <div style={{ marginTop: 6, maxHeight: 160, overflowY: "auto", border: `1px solid ${colors.divider}`, borderRadius: 4 }}>
          {results.map((r, i) => (
            <div
              key={i}
              onClick={() => add(r)}
              style={{
                padding: "6px 8px",
                fontSize: 11.5,
                color: colors.text,
                borderBottom: i < results.length - 1 ? `1px solid ${colors.divider}` : "none",
                cursor: "pointer",
              }}
            >
              + {r.display_name}
            </div>
          ))}
        </div>
      )}
      {selected.length > 0 && (
        <>
          <div style={{ ...mono, fontSize: 9.5, letterSpacing: "0.08em", color: colors.textFaint, margin: "10px 0 4px" }}>
            {selected.length} LOCATION{selected.length > 1 ? "S" : ""} SELECTED
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
            {selected.map((r, i) => (
              <span
                key={i}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 5,
                  padding: "3px 6px",
                  background: colors.tealTint,
                  borderRadius: 4,
                  ...mono,
                  fontSize: 10.5,
                  color: colors.text,
                }}
              >
                {shortName(r)}
                <button
                  onClick={() => remove(i)}
                  style={{ background: "none", border: "none", color: colors.textFaint, cursor: "pointer", fontSize: 11, padding: 0 }}
                  title="Remove"
                >
                  ✕
                </button>
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
