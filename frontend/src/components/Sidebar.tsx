import type { AntennaSpec, DectNode, GeocodeResult, NodeType, Params } from "../types";
import { ETSI_MAX_TX_POWER_DBM } from "../types";
import { colors, mono } from "../theme";
import InfoTooltip from "./InfoTooltip";
import AddSuburbButton from "./AddSuburbButton";

interface Props {
  nodes: DectNode[];
  rolesById: Record<string, NodeType>;
  params: Params;
  onParamsChange: (p: Params) => void;
  placeMode: boolean;
  onPlaceMode: (mode: boolean) => void;
  onImportClick: () => void;
  onAddSuburbs: (locations: GeocodeResult[]) => void;
  selectedId: string | null;
  onSelect: (id: string) => void;
  estRun: string;
}

const sectionLabel: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: "0.11em",
  color: colors.textMuted,
};
const fieldLabel: React.CSSProperties = {
  ...mono,
  fontSize: 10,
  letterSpacing: "0.08em",
  color: colors.textFaint,
};
const selectStyle: React.CSSProperties = {
  height: 29,
  border: `1px solid ${colors.border}`,
  borderRadius: 4,
  background: colors.panelBg,
  ...mono,
  fontSize: 11,
  color: colors.text,
  padding: "0 6px",
};
const inputStyle: React.CSSProperties = { ...selectStyle, padding: "0 8px" };

const TYPE_LABEL: Record<NodeType, string> = { sink: "SINK", relay: "RELAY", leaf: "LEAF" };
const TYPE_TAG_BG: Record<NodeType, string> = { sink: colors.teal, relay: colors.tealTint, leaf: "#e9e7e0" };
const TYPE_TAG_FG: Record<NodeType, string> = { sink: colors.panelBg, relay: colors.tealDark, leaf: colors.textMuted };

export default function Sidebar({
  nodes,
  rolesById,
  params,
  onParamsChange,
  placeMode,
  onPlaceMode,
  onImportClick,
  onAddSuburbs,
  selectedId,
  onSelect,
  estRun,
}: Props) {
  const setParam = <K extends keyof Params>(key: K, value: Params[K]) =>
    onParamsChange({ ...params, [key]: value });
  const setAntenna = <K extends keyof AntennaSpec>(key: K, value: AntennaSpec[K]) =>
    onParamsChange({ ...params, antenna: { ...params.antenna, [key]: value } });

  const placeBtnStyle = (active: boolean): React.CSSProperties => ({
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    height: 29,
    border: `1px solid ${active ? colors.text : colors.border}`,
    background: active ? colors.text : colors.panelBg,
    color: active ? colors.panelBg : colors.textMuted,
    borderRadius: 4,
    ...mono,
    fontSize: 10.5,
    fontWeight: 600,
    cursor: "pointer",
  });

  return (
    <div
      style={{
        width: 320,
        flex: "none",
        display: "flex",
        flexDirection: "column",
        background: colors.panelBg,
        borderRight: `1px solid ${colors.border}`,
        minHeight: 0,
      }}
    >
      <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
        {/* TOPOLOGY */}
        <div style={{ padding: "14px 14px 12px", borderBottom: `1px solid ${colors.divider}` }}>
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 10 }}>
            <div style={sectionLabel}>TOPOLOGY</div>
            <div style={{ ...mono, fontSize: 10.5, color: colors.textFaint }}>{nodes.length} NODES</div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6, marginBottom: 6 }}>
            <button style={placeBtnStyle(placeMode)} onClick={() => onPlaceMode(!placeMode)}>
              + NODE
            </button>
            <button style={placeBtnStyle(false)} onClick={onImportClick}>
              IMPORT CSV
            </button>
            <AddSuburbButton buttonStyle={{ ...placeBtnStyle(false), width: "100%" }} onAdd={onAddSuburbs} />
          </div>
          <div style={{ ...fieldLabel, marginBottom: 10 }}>
            Role (sink / router / leaf) is decided by the simulation by default — select a node on the map to
            override its type, TX power, or next hop.
          </div>
          <div style={{ display: "flex", flexDirection: "column", border: `1px solid ${colors.divider}`, borderRadius: 4, maxHeight: 238, overflowY: "auto" }}>
            {nodes.map((n) => (
              <div
                key={n.id}
                onClick={() => onSelect(n.id)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "6px 9px",
                  borderBottom: `1px solid ${colors.bg}`,
                  background: selectedId === n.id ? colors.tealTint : "transparent",
                  cursor: "pointer",
                }}
              >
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: colors.green, flex: "none" }} />
                <span style={{ ...mono, fontSize: 11.5, fontWeight: 500, color: colors.text, width: 64 }}>{n.id}</span>
                {rolesById[n.id] ? (
                  <span
                    style={{
                      ...mono,
                      fontSize: 9.5,
                      fontWeight: 600,
                      letterSpacing: "0.07em",
                      padding: "1.5px 6px",
                      borderRadius: 3,
                      background: TYPE_TAG_BG[rolesById[n.id]],
                      color: TYPE_TAG_FG[rolesById[n.id]],
                    }}
                  >
                    {TYPE_LABEL[rolesById[n.id]]}
                  </span>
                ) : (
                  <span style={{ ...mono, fontSize: 9.5, color: colors.textFaint }}>not simulated</span>
                )}
                <span style={{ flex: 1 }} />
                <span style={{ ...mono, fontSize: 10.5, color: colors.textFaint }}>{n.h} m</span>
              </div>
            ))}
          </div>
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              marginTop: 10,
              ...mono,
              fontSize: 10.5,
              color: colors.textMuted,
              cursor: "pointer",
            }}
          >
            <input
              type="checkbox"
              checked={params.auto_connect}
              onChange={(e) => setParam("auto_connect", e.target.checked)}
            />
            Auto-promote sinks (promote existing nodes to sink so every node is connected)
          </label>
        </div>

        {/* RADIO / PHY */}
        <div style={{ padding: 14, borderBottom: `1px solid ${colors.divider}`, display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={sectionLabel}>RADIO · PHY</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <label style={fieldLabel}>BAND</label>
              <select style={selectStyle} value={params.band} onChange={(e) => setParam("band", e.target.value as Params["band"])}>
                <option value="b1">1.9 GHz (EU, n1900)</option>
                <option value="b2">902 MHz (US)</option>
              </select>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <label style={fieldLabel}>CHANNEL</label>
              <select style={selectStyle} value={params.channel} onChange={(e) => setParam("channel", e.target.value)}>
                <option value="1657">n=1657 · 1881.8 MHz</option>
                <option value="1658">n=1658 · 1883.5 MHz</option>
                <option value="1659">n=1659 · 1885.2 MHz</option>
                <option value="1660">n=1660 · 1887.0 MHz</option>
                <option value="1661">n=1661 · 1888.7 MHz</option>
                <option value="1662">n=1662 · 1890.4 MHz</option>
                <option value="1663">n=1663 · 1892.2 MHz</option>
                <option value="1664">n=1664 · 1893.9 MHz</option>
                <option value="1665">n=1665 · 1895.6 MHz</option>
                <option value="1666">n=1666 · 1897.3 MHz</option>
              </select>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <label style={fieldLabel}>SUBCARRIER μ</label>
              <select style={selectStyle} value={params.mu} onChange={(e) => setParam("mu", e.target.value as Params["mu"])}>
                <option value="1">μ=1 · 1.728 MHz</option>
                <option value="2">μ=2 · 3.456 MHz</option>
                <option value="4">μ=4 · 6.912 MHz</option>
              </select>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <label style={fieldLabel}>MCS</label>
              <select style={selectStyle} value={params.mcs} onChange={(e) => setParam("mcs", e.target.value)}>
                <option value="0">MCS-0 · BPSK 1/2</option>
                <option value="1">MCS-1 · QPSK 1/2</option>
                <option value="2">MCS-2 · QPSK 3/4</option>
                <option value="4">MCS-4 · 16QAM 3/4</option>
              </select>
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <label style={{ ...fieldLabel, display: "flex", alignItems: "center", gap: 5 }}>
                MAX TX POWER (power-control ceiling)
                <InfoTooltip text="The engine solves each link's actual transmit power to hit its target BLER, capped at this ceiling — it does not simply broadcast every link at this value." />
              </label>
              <span style={{ ...mono, fontSize: 11.5, fontWeight: 600, color: colors.tealDark }}>
                {params.max_tx_power_dbm} dBm
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={ETSI_MAX_TX_POWER_DBM}
              step={1}
              value={params.max_tx_power_dbm}
              onChange={(e) => setParam("max_tx_power_dbm", parseInt(e.target.value, 10))}
              style={{ width: "100%", height: 16, cursor: "pointer" }}
            />
            <div style={{ display: "flex", justifyContent: "space-between", ...mono, fontSize: 9.5, color: colors.textFaint }}>
              <span>0</span>
              <span>ETSI limit {ETSI_MAX_TX_POWER_DBM}</span>
            </div>
          </div>
        </div>

        {/* ANTENNA */}
        <div style={{ padding: 14, borderBottom: `1px solid ${colors.divider}`, display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <div style={sectionLabel}>ANTENNA</div>
              <InfoTooltip text="Default: realistic ~5 dBi outdoor omni collinear for 1.9 GHz (20° vertical beamwidth — omni in azimuth only, tapers toward zenith/nadir)." />
            </div>
            <span
              style={{
                ...mono,
                fontSize: 9.5,
                padding: "1.5px 6px",
                background: colors.tealTint,
                color: colors.tealDark,
                borderRadius: 3,
                fontWeight: 600,
              }}
            >
              SHARED, ALL RADIOS
            </span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <label style={fieldLabel}>GAIN (dBi)</label>
              <input
                style={inputStyle}
                type="number"
                step={0.5}
                value={params.antenna.gain_dbi}
                onChange={(e) => setAntenna("gain_dbi", parseFloat(e.target.value))}
              />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <label style={fieldLabel}>ELEV. BEAMWIDTH (°)</label>
              <input
                style={inputStyle}
                type="number"
                step={1}
                value={params.antenna.elevation_beamwidth_deg}
                onChange={(e) => setAntenna("elevation_beamwidth_deg", parseFloat(e.target.value))}
              />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <label style={fieldLabel}>FRONT/BACK (dB)</label>
              <input
                style={inputStyle}
                type="number"
                step={1}
                value={params.antenna.front_to_back_db}
                onChange={(e) => setAntenna("front_to_back_db", parseFloat(e.target.value))}
              />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <label style={fieldLabel}>CABLE LOSS (dB)</label>
              <input
                style={inputStyle}
                type="number"
                step={0.5}
                value={params.antenna.cable_loss_db}
                onChange={(e) => setAntenna("cable_loss_db", parseFloat(e.target.value))}
              />
            </div>
          </div>
        </div>

        {/* PROPAGATION */}
        <div style={{ padding: 14, borderBottom: `1px solid ${colors.divider}`, display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={sectionLabel}>PROPAGATION</div>
            <span
              style={{
                ...mono,
                fontSize: 9.5,
                padding: "1.5px 6px",
                background: colors.tealTint,
                color: colors.tealDark,
                borderRadius: 3,
                fontWeight: 600,
              }}
            >
              TR 38.901 + real geometry
            </span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <label style={fieldLabel}>LOSS MODEL</label>
            <select style={selectStyle} value={params.model} onChange={(e) => setParam("model", e.target.value as Params["model"])}>
              <option value="uma">3GPP UMa (dual-slope, LOS/NLOS)</option>
              <option value="umi">3GPP UMi Street Canyon</option>
              <option value="logd">Log-distance (simplified)</option>
            </select>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <label style={fieldLabel}>SHADOWING σ</label>
              <input
                style={inputStyle}
                value={params.sigma}
                onChange={(e) => setParam("sigma", parseFloat(e.target.value) || 0)}
              />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <label style={fieldLabel}>NOISE FIG</label>
              <input style={inputStyle} value={params.nf} onChange={(e) => setParam("nf", parseFloat(e.target.value) || 0)} />
            </div>
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: 12, color: colors.textMuted }}>
            <input
              type="checkbox"
              checked={params.o2i}
              onChange={(e) => setParam("o2i", e.target.checked)}
              style={{ accentColor: colors.teal, width: 13, height: 13 }}
            />
            Building entry loss (O2I, OSM footprints)
          </label>
        </div>

        {/* TRAFFIC */}
        <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={sectionLabel}>TRAFFIC · HARQ</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <label style={fieldLabel}>PAYLOAD (B)</label>
              <input style={inputStyle} value={params.payload} onChange={(e) => setParam("payload", parseInt(e.target.value, 10) || 0)} />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <label style={fieldLabel}>INTERVAL (s)</label>
              <input style={inputStyle} value={params.interval} onChange={(e) => setParam("interval", parseFloat(e.target.value) || 0)} />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <label style={fieldLabel}>DURATION (s)</label>
              <input style={inputStyle} value={params.duration} onChange={(e) => setParam("duration", parseFloat(e.target.value) || 0)} />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <label style={fieldLabel}>HARQ RETX (IR combining)</label>
              <select style={selectStyle} value={params.harq} onChange={(e) => setParam("harq", e.target.value as Params["harq"])}>
                <option value="0">0</option>
                <option value="2">2</option>
                <option value="4">4</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      <div
        style={{
          flex: "none",
          padding: "10px 14px",
          borderTop: `1px solid ${colors.border}`,
          background: colors.bg,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <span style={{ ...mono, fontSize: 10, letterSpacing: "0.06em", color: colors.textFaint }}>EST. RUN</span>
        <span style={{ ...mono, fontSize: 10.5, color: colors.textMuted }}>{estRun}</span>
      </div>
    </div>
  );
}
