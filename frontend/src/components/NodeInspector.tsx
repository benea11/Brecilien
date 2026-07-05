import { colors, mono } from "../theme";
import type { DectNode, LinkMetric, NodeMetric, NodeType } from "../types";

type ForcedRole = "sink" | "relay";

interface Props {
  node: DectNode;
  nodes: DectNode[];
  role?: NodeType;
  metric?: NodeMetric;
  linkMetric?: LinkMetric;
  routeLinks?: LinkMetric[];
  onClear: () => void;
  onDelete: () => void;
  onHeightChange: (h: number) => void;
  onForcedRoleChange: (role: ForcedRole | null) => void;
  onTxPowerChange: (dbm: number | null) => void;
  onStaticParentChange: (parentId: string | null) => void;
}

const TYPE_LABEL: Record<NodeType, string> = { sink: "SINK", relay: "RELAY", leaf: "LEAF" };
const TYPE_COLOR: Record<NodeType, string> = { sink: colors.teal, relay: colors.text, leaf: colors.textMuted };
const TYPE_TAG_BG: Record<NodeType, string> = { sink: colors.teal, relay: colors.tealTint, leaf: "#e9e7e0" };
const TYPE_TAG_FG: Record<NodeType, string> = { sink: colors.panelBg, relay: colors.tealDark, leaf: colors.textMuted };

function fmtPdr(p: number | null | undefined): string {
  if (p == null) return "—";
  return (p * 100).toFixed(1) + "%";
}

const ROLE_TOGGLE_OPTIONS: { value: ForcedRole | null; label: string }[] = [
  { value: null, label: "AUTO" },
  { value: "sink", label: "SINK" },
  { value: "relay", label: "ROUTER" },
];

export default function NodeInspector({
  node,
  nodes,
  role,
  metric,
  linkMetric,
  routeLinks,
  onClear,
  onDelete,
  onHeightChange,
  onForcedRoleChange,
  onTxPowerChange,
  onStaticParentChange,
}: Props) {
  const pdr = metric?.e2e_pdr;
  const pdrColor = pdr == null ? colors.textFaint : pdr >= 0.97 ? colors.green : pdr >= 0.9 ? colors.amber : colors.red;
  const route = metric?.route ?? [];
  const hops = routeLinks ?? [];
  const otherNodes = nodes.filter((n) => n.id !== node.id);

  return (
    <div
      data-screen-label="Node inspector"
      style={{
        position: "absolute",
        bottom: 34,
        left: 12,
        zIndex: 6,
        width: 270,
        background: colors.panelBg,
        border: `1px solid ${colors.border}`,
        borderRadius: 6,
        boxShadow: "0 4px 14px rgba(33,31,26,0.13)",
        overflow: "hidden",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", borderBottom: `1px solid ${colors.divider}`, background: colors.bg }}>
        <span style={{ width: 8, height: 8, borderRadius: 2, background: role ? TYPE_COLOR[role] : colors.textFaint, display: "inline-block" }} />
        <span style={{ ...mono, fontSize: 12, fontWeight: 600, color: colors.text }}>{node.id}</span>
        {role ? (
          <span
            style={{
              ...mono,
              fontSize: 9.5,
              fontWeight: 600,
              letterSpacing: "0.07em",
              padding: "1.5px 6px",
              borderRadius: 3,
              background: TYPE_TAG_BG[role],
              color: TYPE_TAG_FG[role],
            }}
          >
            {TYPE_LABEL[role]}
          </span>
        ) : (
          <span style={{ ...mono, fontSize: 9.5, color: colors.textFaint }}>role: run simulation</span>
        )}
        <span style={{ flex: 1 }} />
        <button onClick={onClear} style={{ background: "none", border: "none", color: colors.textFaint, fontSize: 13, cursor: "pointer", padding: "0 2px" }}>
          ✕
        </button>
      </div>
      <div style={{ padding: "9px 12px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "7px 10px", ...mono, fontSize: 11 }}>
        <div>
          <div style={{ fontSize: 9.5, letterSpacing: "0.07em", color: colors.textFaint }}>POSITION (drag on map)</div>
          <div style={{ color: colors.text }}>{node.lat.toFixed(4)}, {node.lon.toFixed(4)}</div>
        </div>
        <div>
          <div style={{ fontSize: 9.5, letterSpacing: "0.07em", color: colors.textFaint }}>MOUNT (m AGL)</div>
          <input
            type="number"
            step={0.5}
            value={node.h}
            onChange={(e) => {
              const v = parseFloat(e.target.value);
              if (!Number.isNaN(v)) onHeightChange(v);
            }}
            style={{
              width: "100%",
              height: 20,
              border: `1px solid ${colors.border}`,
              borderRadius: 3,
              background: colors.panelBg,
              ...mono,
              fontSize: 11,
              color: colors.text,
              padding: "0 4px",
            }}
          />
        </div>
        <div style={{ gridColumn: "1 / -1" }}>
          <div style={{ fontSize: 9.5, letterSpacing: "0.07em", color: colors.textFaint }}>TYPE (override)</div>
          <div style={{ display: "flex", gap: 4 }}>
            {ROLE_TOGGLE_OPTIONS.map((opt) => {
              const active = (node.forced_role ?? null) === opt.value;
              return (
                <button
                  key={opt.label}
                  onClick={() => onForcedRoleChange(opt.value)}
                  style={{
                    flex: 1,
                    height: 20,
                    border: `1px solid ${active ? colors.teal : colors.border}`,
                    background: active ? colors.teal : colors.panelBg,
                    color: active ? colors.panelBg : colors.textMuted,
                    borderRadius: 3,
                    ...mono,
                    fontSize: 9.5,
                    fontWeight: 600,
                    letterSpacing: "0.05em",
                    cursor: "pointer",
                  }}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 9.5, letterSpacing: "0.07em", color: colors.textFaint }}>PARENT</div>
          <div style={{ color: colors.text }}>{metric?.parent ?? (role === "sink" ? "— (root)" : "UNREACHABLE")}</div>
        </div>
        <div>
          <div style={{ fontSize: 9.5, letterSpacing: "0.07em", color: colors.textFaint }}>LINK RSSI</div>
          <div style={{ color: colors.text }}>{linkMetric ? linkMetric.rssi_dbm.toFixed(1) + " dBm" : "—"}</div>
        </div>
        <div>
          <div style={{ fontSize: 9.5, letterSpacing: "0.07em", color: colors.textFaint }}>
            TX POWER (dBm{node.tx_power_dbm == null ? ", auto" : ""})
          </div>
          <input
            type="number"
            step={0.5}
            min={0}
            max={23}
            value={node.tx_power_dbm ?? ""}
            placeholder={linkMetric ? linkMetric.tx_power_dbm.toFixed(1) : "auto"}
            onChange={(e) => {
              if (e.target.value === "") {
                onTxPowerChange(null);
                return;
              }
              const v = parseFloat(e.target.value);
              if (!Number.isNaN(v)) onTxPowerChange(v);
            }}
            style={{
              width: "100%",
              height: 20,
              border: `1px solid ${colors.border}`,
              borderRadius: 3,
              background: colors.panelBg,
              ...mono,
              fontSize: 11,
              color: colors.text,
              padding: "0 4px",
            }}
          />
        </div>
        <div>
          <div style={{ fontSize: 9.5, letterSpacing: "0.07em", color: colors.textFaint }}>LOS</div>
          <div style={{ color: colors.text }}>{linkMetric ? (linkMetric.los ? "LOS" : "NLOS") : "—"}</div>
        </div>
        <div style={{ gridColumn: "1 / -1" }}>
          <div style={{ fontSize: 9.5, letterSpacing: "0.07em", color: colors.textFaint }}>NEXT HOP (override)</div>
          <select
            value={node.static_parent ?? ""}
            onChange={(e) => onStaticParentChange(e.target.value === "" ? null : e.target.value)}
            style={{
              width: "100%",
              height: 20,
              border: `1px solid ${colors.border}`,
              borderRadius: 3,
              background: colors.panelBg,
              ...mono,
              fontSize: 11,
              color: colors.text,
              padding: "0 4px",
            }}
          >
            <option value="">AUTO (from simulation)</option>
            {otherNodes.map((n) => (
              <option key={n.id} value={n.id}>
                {n.id}
              </option>
            ))}
          </select>
        </div>
        <div style={{ gridColumn: "1 / -1" }}>
          <div style={{ fontSize: 9.5, letterSpacing: "0.07em", color: colors.textFaint }}>ROUTE</div>
          {role === "sink" ? (
            <div style={{ color: colors.tealDark }}>root</div>
          ) : !route.length ? (
            <div style={{ color: colors.tealDark }}>no route</div>
          ) : (
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "2px 4px" }}>
              {route.map((hopId, i) => {
                const hop = hops[i];
                return (
                  <span key={hopId} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                    <span style={{ color: colors.tealDark }}>{hopId}</span>
                    {hop && (
                      <span style={{ fontSize: 9.5, color: colors.textFaint }}>
                        → {hop.rssi_dbm.toFixed(1)} dBm →
                      </span>
                    )}
                  </span>
                );
              })}
            </div>
          )}
        </div>
        <div>
          <div style={{ fontSize: 9.5, letterSpacing: "0.07em", color: colors.textFaint }}>E2E PDR</div>
          <div style={{ fontWeight: 600, color: pdrColor }}>{role === "sink" ? "—" : fmtPdr(pdr)}</div>
        </div>
        <div>
          <div style={{ fontSize: 9.5, letterSpacing: "0.07em", color: colors.textFaint }}>E2E LATENCY</div>
          <div style={{ color: colors.text }}>{metric?.e2e_latency_ms != null ? metric.e2e_latency_ms.toFixed(1) + " ms" : "—"}</div>
        </div>
      </div>
      <div style={{ padding: "0 12px 10px", display: "flex", gap: 6 }}>
        <button
          onClick={onDelete}
          style={{
            flex: 1,
            height: 27,
            border: `1px solid ${colors.red}`,
            color: colors.red,
            background: colors.panelBg,
            borderRadius: 4,
            ...mono,
            fontSize: 10.5,
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          DELETE NODE
        </button>
      </div>
    </div>
  );
}
