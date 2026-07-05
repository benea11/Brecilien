import { useEffect, useRef, useState } from "react";
import { deleteProject, listProjects } from "../api";
import { colors, mono } from "../theme";
import type { GeocodeResult, ProjectSummary } from "../types";
import LocationMultiSearch, { shortName } from "./LocationMultiSearch";

interface Props {
  currentProjectId: string;
  currentProjectName: string;
  onSwitchProject: (id: string) => void;
  onCreateProject: (name: string, locations: GeocodeResult[], addMvSubstations: boolean) => void;
}

function defaultProjectName(locations: GeocodeResult[]): string {
  return locations.map(shortName).join(" + ").slice(0, 60);
}

export default function ProjectMenu({ currentProjectId, currentProjectName, onSwitchProject, onCreateProject }: Props) {
  const [open, setOpen] = useState(false);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [addMvSubstations, setAddMvSubstations] = useState(false);
  const [selected, setSelected] = useState<GeocodeResult[]>([]);
  const [name, setName] = useState("");
  const [nameTouched, setNameTouched] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    listProjects().then(setProjects).catch(() => setProjects([]));
  }, [open]);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  useEffect(() => {
    if (!nameTouched) setName(defaultProjectName(selected));
  }, [selected, nameTouched]);

  function resetMenu() {
    setSelected([]);
    setAddMvSubstations(false);
    setName("");
    setNameTouched(false);
  }

  function createFromSelection() {
    if (selected.length === 0) return;
    onCreateProject(name.trim() || defaultProjectName(selected), selected, addMvSubstations);
    setOpen(false);
    resetMenu();
  }

  async function removeProject(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    if (id === currentProjectId) return;
    await deleteProject(id).catch(() => {});
    setProjects((ps) => ps.filter((p) => p.id !== id));
  }

  return (
    <div ref={rootRef} style={{ position: "relative" }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          background: "none",
          border: "none",
          cursor: "pointer",
          ...mono,
          fontSize: 11,
          color: colors.textMuted,
          padding: 0,
        }}
      >
        <span style={{ color: colors.textFaint }}>PROJECT</span>
        <span style={{ color: colors.text, fontWeight: 500 }}>{currentProjectName}</span>
        <span style={{ fontSize: 9 }}>▾</span>
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            top: 28,
            left: 0,
            zIndex: 20,
            width: 340,
            background: colors.panelBg,
            border: `1px solid ${colors.border}`,
            borderRadius: 6,
            boxShadow: "0 4px 14px rgba(33,31,26,0.18)",
            overflow: "hidden",
          }}
        >
          <div style={{ padding: 10, borderBottom: `1px solid ${colors.divider}` }}>
            <div style={{ ...mono, fontSize: 9.5, letterSpacing: "0.08em", color: colors.textFaint, marginBottom: 6 }}>
              NEW PROJECT — SEARCH LOCATIONS
            </div>
            <LocationMultiSearch selected={selected} onChange={setSelected} autoFocus />

            {selected.length > 0 && (
              <>
                {selected.some((r) => r.country_code === "fr") && (
                  <label
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      marginTop: 8,
                      ...mono,
                      fontSize: 10.5,
                      color: colors.textMuted,
                      cursor: "pointer",
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={addMvSubstations}
                      onChange={(e) => setAddMvSubstations(e.target.checked)}
                    />
                    Add MV substations (Enedis, France only -- applied per selected location)
                  </label>
                )}

                <input
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                    setNameTouched(true);
                  }}
                  placeholder="Project name"
                  style={{
                    width: "100%",
                    height: 27,
                    marginTop: 8,
                    border: `1px solid ${colors.border}`,
                    borderRadius: 4,
                    background: colors.bg,
                    ...mono,
                    fontSize: 11,
                    color: colors.text,
                    padding: "0 8px",
                  }}
                />
                <button
                  onClick={createFromSelection}
                  style={{
                    width: "100%",
                    height: 28,
                    marginTop: 6,
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
                  CREATE PROJECT
                </button>
              </>
            )}
          </div>
          <div style={{ maxHeight: 220, overflowY: "auto" }}>
            <div style={{ ...mono, fontSize: 9.5, letterSpacing: "0.08em", color: colors.textFaint, padding: "8px 10px 4px" }}>
              EXISTING PROJECTS
            </div>
            {projects.map((p) => (
              <div
                key={p.id}
                onClick={() => {
                  onSwitchProject(p.id);
                  setOpen(false);
                }}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "6px 10px",
                  cursor: "pointer",
                  background: p.id === currentProjectId ? colors.tealTint : "transparent",
                  ...mono,
                  fontSize: 11.5,
                }}
              >
                <span style={{ flex: 1, color: colors.text }}>{p.name}</span>
                {p.id !== currentProjectId && (
                  <button
                    onClick={(e) => removeProject(e, p.id)}
                    style={{ background: "none", border: "none", color: colors.textFaint, cursor: "pointer", fontSize: 12 }}
                    title="Delete project"
                  >
                    ✕
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
