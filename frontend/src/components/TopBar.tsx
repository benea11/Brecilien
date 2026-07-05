import { colors, mono } from "../theme";
import ProjectMenu from "./ProjectMenu";
import type { GeocodeResult } from "../types";

interface Props {
  projectId: string;
  projectName: string;
  running: boolean;
  onRun: () => void;
  onSwitchProject: (id: string) => void;
  onCreateProject: (name: string, locations: GeocodeResult[], addMvSubstations: boolean) => void;
  onShowModelInfo: () => void;
}

export default function TopBar({ projectId, projectName, running, onRun, onSwitchProject, onCreateProject, onShowModelInfo }: Props) {
  return (
    <div
      style={{
        height: 48,
        flex: "none",
        display: "flex",
        alignItems: "center",
        gap: 14,
        padding: "0 14px",
        background: colors.panelBg,
        borderBottom: `1px solid ${colors.border}`,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div
          style={{
            width: 22,
            height: 22,
            background: colors.teal,
            borderRadius: 4,
            display: "grid",
            placeItems: "center",
          }}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <polygon points="8,1.5 12,7 4,7" fill={colors.panelBg} />
            <polygon points="8,5 13,11.5 3,11.5" fill={colors.panelBg} />
            <rect x="7" y="11.5" width="2" height="3" fill={colors.panelBg} />
          </svg>
        </div>
        <div style={{ fontWeight: 700, fontSize: 14, letterSpacing: "0.02em" }}>Brécilien</div>
        <div style={{ width: 1, height: 18, background: colors.divider }} />
        <div style={{ ...mono, fontSize: 10.5, letterSpacing: "0.09em", color: colors.textMuted }}>
          DECT-2020 NR+ LINK SIMULATOR
        </div>
      </div>
      <div style={{ flex: 1 }} />
      <ProjectMenu
        currentProjectId={projectId}
        currentProjectName={projectName}
        onSwitchProject={onSwitchProject}
        onCreateProject={onCreateProject}
      />
      <div style={{ width: 1, height: 18, background: colors.divider }} />
      <button
        onClick={onShowModelInfo}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          padding: "3px 9px",
          border: `1px solid ${colors.divider}`,
          borderRadius: 4,
          ...mono,
          fontSize: 10.5,
          color: colors.textMuted,
          background: colors.bg,
          cursor: "pointer",
        }}
        title="How the propagation model works"
      >
        <span style={{ width: 6, height: 6, borderRadius: "50%", background: colors.green, display: "inline-block" }} />
        ENGINE&nbsp;dect-phy-sim v1.0 (Python/TR 38.901)
        <span style={{ color: colors.teal, fontWeight: 700 }}>ⓘ</span>
      </button>
      <button
        onClick={onRun}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          height: 32,
          padding: "0 16px",
          background: running ? colors.textMuted : colors.teal,
          color: colors.panelBg,
          border: "none",
          borderRadius: 4,
          ...mono,
          fontSize: 11.5,
          fontWeight: 600,
          letterSpacing: "0.07em",
          cursor: "pointer",
        }}
      >
        <span style={{ fontSize: 9 }}>▶</span>
        {running ? "RUNNING…" : "RUN SIMULATION"}
      </button>
    </div>
  );
}
