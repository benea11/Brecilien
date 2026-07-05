import type { CSSProperties } from "react";
import { colors, mono, sans } from "../theme";

interface Props {
  onClose: () => void;
}

const h2: CSSProperties = {
  ...mono,
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: "0.09em",
  color: colors.tealDark,
  marginTop: 22,
  marginBottom: 6,
};
const p: CSSProperties = { ...sans, fontSize: 12.5, lineHeight: 1.65, color: colors.textMuted, margin: "0 0 10px" };
const ul: CSSProperties = { ...sans, fontSize: 12.5, lineHeight: 1.65, color: colors.textMuted, margin: "0 0 10px", paddingLeft: 18 };
const code: CSSProperties = {
  ...mono,
  fontSize: 11,
  background: colors.tealTint,
  color: colors.tealDark,
  padding: "1px 5px",
  borderRadius: 3,
};

export default function PropagationModelInfo({ onClose }: Props) {
  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 50,
        background: "rgba(33,31,26,0.4)",
        display: "grid",
        placeItems: "center",
        padding: 24,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "min(760px, 100%)",
          maxHeight: "88vh",
          background: colors.panelBg,
          border: `1px solid ${colors.border}`,
          borderRadius: 8,
          boxShadow: "0 12px 40px rgba(33,31,26,0.3)",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            padding: "12px 18px",
            borderBottom: `1px solid ${colors.divider}`,
            flex: "none",
          }}
        >
          <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: "0.06em", color: colors.text }}>
            HOW THE PROPAGATION MODEL WORKS
          </div>
          <div style={{ flex: 1 }} />
          <button
            onClick={onClose}
            style={{ background: "none", border: "none", color: colors.textFaint, fontSize: 16, cursor: "pointer", padding: "0 2px" }}
          >
            ✕
          </button>
        </div>

        <div style={{ overflowY: "auto", padding: "16px 22px 26px" }}>
          <p style={p}>
            Every link in the mesh (and every cell of the coverage heatmap) is scored by the same large-scale
            link budget, which combines six factors into one number — lower is better:
          </p>
          <div
            style={{
              ...mono,
              fontSize: 11.5,
              color: colors.text,
              background: colors.bg,
              border: `1px solid ${colors.divider}`,
              borderRadius: 5,
              padding: "9px 12px",
              marginBottom: 10,
            }}
          >
            loss = pathloss + diffraction + O2I + shadowing − antenna gain
          </div>
          <p style={p}>
            That total, plus the thermal noise floor, is what the power-control step and the Monte Carlo
            link-level simulation (below) use to solve transmit power and predict PDR/latency. Each term:
          </p>

          <div style={h2}>1 · BASE PATHLOSS — 3GPP TR 38.901</div>
          <p style={p}>
            The distance-dependent loss comes from the 3GPP TR 38.901 UMa or UMi-Street-Canyon models (or a
            plain log-distance fallback), selected in the <span style={code}>LOSS MODEL</span> dropdown. Both
            3GPP models are dual-slope: below a breakpoint distance (set by the two antennas' effective heights
            and the carrier frequency) loss grows with one exponent, and beyond it with a steeper one. The NLOS
            case takes the larger of the LOS formula and a separate NLOS regression, per spec. Because DECT
            NR+'s 902 MHz / 1.9 GHz bands sit below where TR 38.901's frequency term was validated, the
            frequency figure is clamped to a 2 GHz floor — a deliberate, conservative choice that slightly
            overstates loss rather than extrapolating the formula outside its validated range.
          </p>

          <div style={h2}>2 · LINE OF SIGHT — real OSM building geometry</div>
          <p style={p}>
            Rather than TR 38.901's statistical LOS-probability formula, this planner checks the actual
            straight line between the two radios against real building footprints (fetched from
            OpenStreetMap) in local ENU meters. If that line's horizontal projection crosses a building's
            outline, and the line's height at the crossing is below that building's height (flat-roof
            assumption), the link is NLOS and the crossing becomes a rooftop-diffraction obstruction (below).
          </p>
          <p style={p}>
            A node placed inside — or right at the edge of — a building footprint is always treated as
            mounted to that building's exterior (a wall or the roof), never embedded within it. So a node's
            own host building can never make its own link NLOS or contribute diffraction loss to it; only
            other buildings genuinely standing between the two radios do that. The host building's effect on
            that link is instead captured entirely by O2I penetration loss (factor 4).
          </p>

          <div style={h2}>3 · ROOFTOP DIFFRACTION — ITU-R P.526 (Deygout)</div>
          <p style={p}>
            When a link is NLOS, each blocking rooftop adds an excess loss on top of the statistical NLOS
            pathloss, via ITU-R P.526's multiple knife-edge diffraction (Deygout method): the most significant
            obstruction becomes the "main edge," and the method recurses on the sub-paths either side of it
            for any remaining obstructions. Two guardrails keep this realistic for dense OSM data, where a
            street-level link can nominally cross dozens of adjacent building footprints: only the 3 most
            significant obstructions are fed into the Deygout calculation, and the total is capped at 30 dB —
            a bounded correction on top of the statistical average, not an unbounded one.
          </p>

          <div style={h2}>4 · BUILDING ENTRY LOSS — O2I (TR 38.901 §7.4.3)</div>
          <p style={p}>
            When the <span style={code}>Building entry loss (O2I)</span> toggle is on and a leaf node's
            position falls inside a building footprint, an outdoor-to-indoor penetration loss is added: a
            low- or high-loss glass/concrete mix (frequency-dependent, per TR 38.901) plus a fixed
            per-metre indoor loss representing the last stretch to the equipment. This models a leaf
            mounted just inside an exterior wall or window, reached from an outdoor infrastructure radio.
          </p>

          <div style={h2}>5 · ANTENNA GAIN &amp; PATTERN</div>
          <p style={p}>
            One antenna spec applies to every radio in the project. It's omnidirectional in azimuth, but not
            in elevation: gain tapers off the further a link's elevation angle sits from the horizon (the same
            vertical-pattern formula TR 38.901 uses for base-station antenna elements), so a leaf almost
            directly under a tall relay sees less antenna gain than one near the horizon. Feeder/connector
            loss and cross-polarization mismatch are subtracted at both ends.
          </p>

          <div style={h2}>6 · CORRELATED SHADOW FADING</div>
          <p style={p}>
            Slow (shadow) fading isn't drawn independently per link — nearby points should see correlated
            clutter loss, the way real shadowing works. One spatially-correlated 2D Gaussian random field is
            synthesized per LOS/NLOS state (different empirical decorrelation distances per TR 38.901 table
            7.4.4-1), and both the node-to-node link budgets and the coverage-heatmap grid sample the same
            field, scaled by the configured <span style={code}>SHADOWING σ</span>.
          </p>

          <div style={h2}>ROUTING: SINK SELECTION &amp; CLUSTER TREE</div>
          <p style={p}>
            There's no fixed backhaul point up front — a sink is picked from siting: the most central node
            mounted above 8 m AGL (a rooftop/mast height, treated as a deliberately-elevated backhaul mount),
            or the single most central node overall if nothing clears that bar. Every other node's route to
            the sink is the shortest cumulative-loss path over a Dijkstra tree built from the real link
            budget of every node pair — not raw distance, since pathloss is logarithmic and a route is
            actually scored on achievable per-hop PDR, the same thing end-to-end delivery depends on. Any
            node can end up relaying for any other; a node's SINK / RELAY / LEAF label in the results panel
            is an observed property of the resulting tree (does it have children, is it the root), not a
            category assigned up front.
          </p>

          <div style={h2}>MANUAL OVERRIDES</div>
          <p style={p}>
            Selecting a node on the map opens an inspector with three optional overrides that pin the
            auto-derived behavior above for that one radio, applied on the next simulation run:
          </p>
          <ul style={ul}>
            <li>
              <span style={code}>TYPE</span> — force <span style={code}>SINK</span> (this node becomes a
              root of the routing forest; multiple simultaneous forced sinks are supported) or{" "}
              <span style={code}>ROUTER</span> (excluded from ever being auto-selected as a sink, but still
              eligible to relay). LEAF stays derived-only — it's never manually assignable.
            </li>
            <li>
              <span style={code}>TX POWER</span> — fixes this node's per-hop transmit power instead of the
              power-control solve below, still clamped to the ETSI 23 dBm limit.
            </li>
            <li>
              <span style={code}>NEXT HOP</span> — pins this node's parent to a specific neighbor instead of
              the cluster tree's pick; every other, unpinned node still routes normally, including through a
              pinned node. A pin that forms a cycle or chains onto a route that never reaches a sink just
              leaves the affected node(s) OFFLINE, same as any other unreachable node.
            </li>
          </ul>

          <div style={h2}>NOISE FLOOR &amp; POWER CONTROL</div>
          <p style={p}>
            The thermal noise floor is kTB plus the configured receiver noise figure. Rather than
            transmitting every link at a fixed power, the engine solves for the minimum transmit power that
            closes each link at its MCS's required SINR plus a margin, capped at the configured power budget
            and the hard ETSI limit of 23 dBm. Links that can't close even at the cap still run at the cap and
            report whatever SINR results — that's what shows up as a weak/offline link. A node with a manual
            TX POWER override (above) skips this solve entirely and transmits at that fixed, still-clamped
            value instead.
          </p>

          <div style={h2}>MONTE CARLO LINK LEVEL: BLER, HARQ &amp; ROUTE COMPOSITION</div>
          <ul style={ul}>
            <li>
              Each trial (and each HARQ round within it) draws an independent frequency-selective fast-fading
              channel — Rician-shaped for LOS links, Rayleigh for NLOS — matched to DECT NR+'s numerology.
            </li>
            <li>
              Per-subcarrier SINR is collapsed to a single mutual-information figure (a capacity-based MIESM
              proxy), which a derived per-MCS BLER curve converts to a decode probability.
            </li>
            <li>
              IR-HARQ combines mutual information across retransmissions, so decode probability improves round
              over round exactly the way real incremental-redundancy combining does.
            </li>
            <li>
              Per-hop PDR and latency are then composed along each leaf's route to the sink (product of hop
              PDRs, sum of hop latencies) to get the end-to-end numbers shown in the results panel.
            </li>
          </ul>

          <div style={h2}>COVERAGE HEATMAP</div>
          <p style={p}>
            Each heatmap cell runs through the same pathloss + LOS/diffraction + shadowing pipeline against
            every infrastructure (sink/relay) node, transmitting at the project's power ceiling, and keeps
            the best resulting RSSI. O2I is intentionally left off for the heatmap — it shows outdoor-equivalent
            coverage across the area rather than the loss to one specific indoor device.
          </p>
        </div>
      </div>
    </div>
  );
}
