import { useState } from "react";
import { generateReport } from "../api";
import { colors, mono } from "../theme";
import type { NodeMetric, Project, SimResult } from "../types";

interface Props {
  project: Project;
  result: SimResult | null;
  open: boolean;
  onToggle: () => void;
  selectedId: string | null;
  onSelectRow: (id: string) => void;
  seed: number;
  sinkIds: string[];
  clusterFilter: string | null;
  onClusterFilterChange: (sinkId: string | null) => void;
}

function fmtPdr(p: number | null): string {
  if (p == null) return "—";
  return (p * 100).toFixed(1) + "%";
}
function pdrColor(p: number | null): string {
  if (p == null) return colors.textMuted;
  return p >= 0.9 ? colors.green : p >= 0.7 ? colors.amber : colors.red;
}

export default function ResultsPanel({
  project,
  result,
  open,
  onToggle,
  selectedId,
  onSelectRow,
  seed,
  sinkIds,
  clusterFilter,
  onClusterFilterChange,
}: Props) {
  const rows: NodeMetric[] = (result?.node_metrics ?? [])
    .filter((m) => m.role !== "sink")
    .filter((m) => !clusterFilter || m.route[m.route.length - 1] === clusterFilter);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  async function handleExportReport(e: React.MouseEvent) {
    e.stopPropagation();
    if (!result || exporting) return;
    setExporting(true);
    setExportError(null);
    try {
      const blob = await generateReport(project, result);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${project.id}-report.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(String(err));
    } finally {
      setExporting(false);
    }
  }

  return (
    <div
      data-screen-label="Results"
      style={{
        position: "absolute",
        top: 12,
        right: 12,
        width: 330,
        zIndex: 5,
        background: colors.panelBg,
        border: `1px solid ${colors.border}`,
        borderRadius: 6,
        boxShadow: "0 4px 14px rgba(33,31,26,0.13)",
        display: "flex",
        flexDirection: "column",
        maxHeight: "calc(100% - 60px)",
        overflow: "hidden",
      }}
    >
      <div
        onClick={onToggle}
        style={{
          flex: "none",
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "9px 12px",
          borderBottom: `1px solid ${open ? colors.divider : "transparent"}`,
          cursor: "pointer",
          background: colors.bg,
        }}
      >
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.11em", color: colors.text }}>
          SIMULATION RESULTS
        </span>
        <span style={{ flex: 1 }} />
        {result && (
          <button
            onClick={handleExportReport}
            disabled={exporting}
            title="Download a PDF report (2D/3D map views + per-node link metrics)"
            style={{
              height: 21,
              padding: "0 8px",
              border: `1px solid ${colors.divider}`,
              borderRadius: 3,
              background: colors.panelBg,
              color: colors.textMuted,
              ...mono,
              fontSize: 9.5,
              fontWeight: 600,
              letterSpacing: "0.04em",
              cursor: exporting ? "wait" : "pointer",
            }}
          >
            {exporting ? "GENERATING…" : "EXPORT PDF"}
          </button>
        )}
        <span style={{ ...mono, fontSize: 10, color: colors.textFaint }}>seed {seed}</span>
        <span style={{ ...mono, fontSize: 11, color: colors.textMuted }}>{open ? "▾" : "▸"}</span>
      </div>
      {exportError && (
        <div style={{ padding: "6px 12px", ...mono, fontSize: 10, color: colors.red, borderBottom: `1px solid ${colors.divider}` }}>
          Report failed: {exportError}
        </div>
      )}
      {open && (
        <div style={{ overflowY: "auto", minHeight: 0 }}>
          {sinkIds.length > 1 && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "6px 12px",
                borderBottom: `1px solid ${colors.divider}`,
              }}
            >
              <span style={{ ...mono, fontSize: 9.5, letterSpacing: "0.08em", color: colors.textFaint }}>CLUSTER</span>
              <select
                value={clusterFilter ?? "all"}
                onChange={(e) => onClusterFilterChange(e.target.value === "all" ? null : e.target.value)}
                style={{
                  flex: 1,
                  height: 22,
                  border: `1px solid ${colors.border}`,
                  borderRadius: 3,
                  background: colors.bg,
                  color: colors.text,
                  ...mono,
                  fontSize: 10.5,
                }}
              >
                <option value="all">All clusters ({sinkIds.length})</option>
                {sinkIds.map((sid) => (
                  <option key={sid} value={sid}>
                    {sid}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", borderBottom: `1px solid ${colors.divider}` }}>
            <div style={{ padding: "10px 12px", borderRight: `1px solid ${colors.bg}` }}>
              <div style={{ ...mono, fontSize: 9.5, letterSpacing: "0.08em", color: colors.textFaint, marginBottom: 3 }}>
                NETWORK PDR
              </div>
              <div style={{ ...mono, fontSize: 19, fontWeight: 600, color: pdrColor(result?.network.pdr ?? null) }}>
                {result ? fmtPdr(result.network.pdr) : "—"}
              </div>
            </div>
            <div style={{ padding: "10px 12px", borderRight: `1px solid ${colors.bg}` }}>
              <div style={{ ...mono, fontSize: 9.5, letterSpacing: "0.08em", color: colors.textFaint, marginBottom: 3 }}>
                MEAN E2E LAT
              </div>
              <div style={{ ...mono, fontSize: 19, fontWeight: 600, color: colors.text }}>
                {result ? result.network.mean_latency_ms.toFixed(0) + " ms" : "—"}
              </div>
            </div>
            <div style={{ padding: "10px 12px" }}>
              <div style={{ ...mono, fontSize: 9.5, letterSpacing: "0.08em", color: colors.textFaint, marginBottom: 3 }}>
                MAX HOPS
              </div>
              <div style={{ ...mono, fontSize: 19, fontWeight: 600, color: colors.text }}>
                {result ? result.network.max_hops : "—"}
              </div>
            </div>
          </div>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              padding: "7px 12px",
              borderBottom: `1px solid ${colors.divider}`,
              ...mono,
              fontSize: 10.5,
              color: colors.textMuted,
            }}
          >
            <span>{result ? `${result.network.delivered.toLocaleString()} / ${result.network.sent.toLocaleString()} pkts delivered` : "—"}</span>
            <span style={{ color: colors.textFaint }}>{result ? `${result.network.events.toLocaleString()} events` : ""}</span>
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "66px 34px 1fr 1fr 52px",
              padding: "6px 12px 4px",
              ...mono,
              fontSize: 9.5,
              letterSpacing: "0.07em",
              color: colors.textFaint,
            }}
          >
            <span>NODE</span>
            <span>HOP</span>
            <span>RSSI</span>
            <span>SNR</span>
            <span style={{ textAlign: "right" }}>PDR</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", paddingBottom: 6 }}>
            {rows.map((r) => (
              <div
                key={r.node_id}
                onClick={() => onSelectRow(r.node_id)}
                style={{
                  display: "grid",
                  gridTemplateColumns: "66px 34px 1fr 1fr 52px",
                  padding: "4px 12px",
                  ...mono,
                  fontSize: 11,
                  background: selectedId === r.node_id ? colors.tealTint : "transparent",
                  cursor: "pointer",
                }}
              >
                <span style={{ fontWeight: 500, color: colors.text }}>{r.node_id}</span>
                <span style={{ color: colors.textMuted }}>{r.offline ? "—" : r.hop}</span>
                <span style={{ color: colors.textMuted }}>{r.offline ? "OFFLINE" : r.rssi_dbm != null ? r.rssi_dbm.toFixed(1) : "—"}</span>
                <span style={{ color: colors.textMuted }}>{r.offline ? "—" : r.snr_db != null ? r.snr_db.toFixed(1) : "—"}</span>
                <span style={{ textAlign: "right", fontWeight: 600, color: pdrColor(r.e2e_pdr) }}>
                  {r.offline ? "—" : fmtPdr(r.e2e_pdr)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
