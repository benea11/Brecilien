"""Builds the report as a single HTML document matching the "DECT Link
Report" Claude Design mock, which MapRenderer.render_pdf then prints to PDF.
Kept as plain string-building (no templating dependency) -- the same style
render.py already uses for the map harness, just with one function per report
section instead of one placeholder swap.
"""
from __future__ import annotations

import base64
from html import escape
from typing import Optional

from ..models import LinkMetric, NodeMetric, Project, SimResult

BG = "#e6e4dd"
SURFACE = "#fbfaf7"
INK = "#211f1a"
MUTED = "#5b574d"
FAINT = "#94907f"
HAIRLINE = "#e3e0d6"
HAIRLINE_STRONG = "#c9c5b8"
TEAL = "#16756c"
TEAL_DARK = "#0c4f49"
TEAL_TINT = "#7fc4bc"
TEAL_TINT_BG = "#d7e8e4"
PDR_GREEN = "#3d8a47"
PDR_ORANGE = "#b3861c"
PDR_RED = "#bb4326"
HEADER_BG = "#211f1a"

WEAK_LINK_COUNT = 3


def _pdr_color(pdr: Optional[float]) -> str:
    if pdr is None:
        return FAINT
    if pdr >= 0.9:
        return PDR_GREEN
    if pdr >= 0.7:
        return PDR_ORANGE
    return PDR_RED


def _fmt(v, digits: int = 1, suffix: str = "") -> str:
    if v is None:
        return "—"
    return f"{v:.{digits}f}{suffix}"


def _b64_png(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode()


def _status(m: NodeMetric) -> tuple[str, str]:
    if m.offline:
        return "OFFLINE", PDR_RED
    if m.role == "sink":
        return "SINK", TEAL
    return "OK", MUTED


HEAD = """<meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  * { box-sizing: border-box; }
  body { margin: 0; background: %(surface)s; font-family: 'Archivo', sans-serif; color: %(ink)s; font-size: 10.5pt; line-height: 1.6; }
  .page { break-before: page; padding-top: 0.15in; }
  .page:first-child { break-before: avoid; padding-top: 0; }
  .mono { font-family: 'JetBrains Mono', monospace; }
  h2.section { font-family: 'Archivo', sans-serif; font-weight: 700; font-size: 15pt; margin: 0 0 2px; display: flex; align-items: baseline; gap: 10px; }
  h2.section .num { font-family: 'JetBrains Mono', monospace; font-size: 10pt; color: %(teal)s; }
  .caption { font-size: 9.5pt; color: %(muted)s; margin-bottom: 12px; }
  table.data { border-collapse: collapse; width: 100%%; font-size: 8.5pt; }
  table.data thead tr { background: %(header_bg)s; color: %(surface)s; }
  table.data thead th { font-family: 'JetBrains Mono', monospace; font-weight: 600; font-size: 7.5pt; letter-spacing: 0.06em; text-transform: uppercase; padding: 6px 10px; }
  table.data tbody td { font-family: 'JetBrains Mono', monospace; padding: 5px 10px; border-bottom: 1px solid %(hairline)s; }
</style>
""" % {
    "surface": SURFACE,
    "ink": INK,
    "teal": TEAL,
    "muted": MUTED,
    "header_bg": HEADER_BG,
    "hairline": HAIRLINE,
}


def build_header_footer(project_name: str, generated_at: str) -> tuple[str, str]:
    name = escape(project_name)
    when = escape(generated_at)
    header = f"""
    <div style="width:100%;display:flex;justify-content:space-between;align-items:baseline;
                padding:0 0.7in;font-family:'JetBrains Mono',monospace;font-size:8.5px;color:{FAINT}">
      <span style="color:{MUTED}"><span style="color:{TEAL};font-weight:600">BRÉCILIEN</span> · DECT NR+ Link Report · {name}</span>
      <span>Generated {when}</span>
    </div>
    """
    footer = f"""
    <div style="width:100%;display:flex;justify-content:space-between;align-items:baseline;
                padding:0 0.7in;font-family:'JetBrains Mono',monospace;font-size:8px;color:{FAINT}">
      <span>brécilien link simulator</span>
      <span>page <span class="pageNumber" style="color:{INK}"></span> of <span class="totalPages" style="color:{INK}"></span></span>
    </div>
    """
    return header, footer


def _cover_section(project_name: str, generated_at: str, net: dict, summary_cells: list[tuple[str, str]]) -> str:
    name = escape(project_name)
    when = escape(generated_at)
    cells_html = "".join(
        f"""<div style="background:{SURFACE};padding:12px 20px">
              <div class="mono" style="font-size:7.5pt;letter-spacing:0.08em;text-transform:uppercase;color:{FAINT}">{escape(label)}</div>
              <div class="mono" style="font-size:13pt;font-weight:600;margin-top:2px">{escape(value)}</div>
            </div>"""
        for label, value in summary_cells
    )
    return f"""
    <div class="page" style="padding-top:0.4in">
      <div class="mono" style="font-size:9pt;letter-spacing:0.12em;color:{TEAL};font-weight:600;text-transform:uppercase">Simulation Report</div>
      <h1 style="font-weight:800;font-size:30pt;line-height:1.1;margin:10px 0 6px;letter-spacing:-0.01em">DECT NR+ Link Report</h1>
      <div style="font-size:14pt;font-weight:500;color:{MUTED};margin-bottom:4px">Project: {name}</div>
      <div class="mono" style="font-size:9pt;color:{FAINT}">Generated {when}</div>
    </div>

    <div style="display:grid;grid-template-columns:1.2fr 1fr 1fr;gap:1px;background:{HAIRLINE_STRONG};border:1px solid {HAIRLINE_STRONG};margin-top:28px">
      <div style="background:{TEAL_DARK};color:{SURFACE};padding:18px 20px">
        <div class="mono" style="font-size:8pt;letter-spacing:0.1em;text-transform:uppercase;color:{TEAL_TINT}">Network PDR</div>
        <div class="mono" style="font-size:26pt;font-weight:700;line-height:1.15">{escape(net['pdr'])}</div>
        <div style="font-size:9pt;color:{TEAL_TINT_BG}">{escape(net['delivered'])} of {escape(net['sent'])} packets delivered</div>
      </div>
      <div style="background:{SURFACE};padding:18px 20px">
        <div class="mono" style="font-size:8pt;letter-spacing:0.1em;text-transform:uppercase;color:{FAINT}">Mean E2E latency</div>
        <div class="mono" style="font-size:26pt;font-weight:700;line-height:1.15;color:{TEAL}">{escape(net['latency'])}</div>
        <div style="font-size:9pt;color:{MUTED}">across all delivered routes</div>
      </div>
      <div style="background:{SURFACE};padding:18px 20px">
        <div class="mono" style="font-size:8pt;letter-spacing:0.1em;text-transform:uppercase;color:{FAINT}">Max hops</div>
        <div class="mono" style="font-size:26pt;font-weight:700;line-height:1.15;color:{TEAL}">{escape(net['maxHops'])}</div>
        <div style="font-size:9pt;color:{MUTED}">deepest route to sink</div>
      </div>
    </div>

    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:{HAIRLINE};border:1px solid {HAIRLINE_STRONG};border-top:none">
      {cells_html}
    </div>

    <div style="margin-top:24px;padding:14px 18px;background:#f2f1ed;border:1px solid {HAIRLINE};font-size:10pt;color:{MUTED}">
      <span style="font-weight:700;color:{INK}">Reading this report.</span>
      Map pages show the simulated mesh topology; link lines are colored by SINR and nodes by predicted end-to-end packet delivery ratio (PDR).
      Detail sections zoom into clusters whose labels overlap in the overview. The appendix lists per-node link metrics.
      PDR is classified <span style="color:{PDR_GREEN};font-weight:700">good ≥ 90%</span>, <span style="color:{PDR_ORANGE};font-weight:700">marginal ≥ 70%</span>, <span style="color:{PDR_RED};font-weight:700">poor &lt; 70%</span>.
    </div>
    """


_LEGEND = f"""
    <div style="display:flex;gap:18px;margin-top:10px;font-family:'JetBrains Mono',monospace;font-size:8pt;color:{MUTED};align-items:center;flex-wrap:wrap">
      <span style="display:flex;align-items:center;gap:6px"><span style="width:10px;height:10px;background:{TEAL};display:inline-block"></span>sink</span>
      <span style="display:flex;align-items:center;gap:6px"><span style="width:10px;height:10px;border-radius:50%;background:{PDR_GREEN};display:inline-block"></span>node · PDR ≥ 90%</span>
      <span style="display:flex;align-items:center;gap:6px"><span style="width:10px;height:10px;border-radius:50%;background:{PDR_ORANGE};display:inline-block"></span>PDR ≥ 70%</span>
      <span style="display:flex;align-items:center;gap:6px"><span style="width:10px;height:10px;border-radius:50%;background:{PDR_RED};display:inline-block"></span>PDR &lt; 70%</span>
      <span style="display:flex;align-items:center;gap:6px"><span style="width:10px;height:10px;border-radius:50%;border:1.5px solid {FAINT};display:inline-block"></span>offline</span>
    </div>
"""


def _map_page(num: str, title: str, caption: str, img_b64: str, legend: bool = False) -> str:
    legend_html = _LEGEND if legend else ""
    return f"""
    <div class="page">
      <h2 class="section"><span class="num">{num}</span>{escape(title)}</h2>
      <div class="caption">{escape(caption)}</div>
      <div style="border:1px solid {HAIRLINE_STRONG}">
        <img src="{img_b64}" style="display:block;width:100%">
      </div>
      {legend_html}
    </div>
    """


def _detail_page(num: str, cluster_ids: str, img_b64: str) -> str:
    return f"""
    <div class="page">
      <h2 class="section"><span class="num">{num}</span>Detail Section — crowded nodes</h2>
      <div class="caption">Nodes <span class="mono" style="color:{INK}">{escape(cluster_ids)}</span> sit closer than one label footprint at overview scale; zoomed for legibility.</div>
      <div style="border:1px solid {HAIRLINE_STRONG}">
        <img src="{img_b64}" style="display:block;width:100%">
      </div>
    </div>
    """


def _topology_summary_page(num: str, link_rows: list[dict], hop_rows: list[dict], weak_links: list[dict]) -> str:
    link_trs = "".join(
        f"""<tr style="background:{r['bg']}">
              <td>{escape(r['child'])}</td><td>{escape(r['parent'])}</td>
              <td style="text-align:right">{r['sinr']}</td>
              <td style="text-align:right;color:{MUTED}">{r['dist']}</td>
            </tr>"""
        for r in link_rows
    )
    hop_bars = "".join(
        f"""<div style="display:grid;grid-template-columns:60px 1fr 30px;gap:8px;align-items:center;margin-bottom:5px;font-family:'JetBrains Mono',monospace;font-size:8.5pt">
              <span style="color:{MUTED}">hop {escape(h['hop'])}</span>
              <span style="height:9px;background:{TEAL_TINT_BG};display:block"><span style="display:block;height:100%;background:{TEAL};width:{h['pct']}%"></span></span>
              <span style="text-align:right;font-weight:600">{h['count']}</span>
            </div>"""
        for h in hop_rows
    )
    weak_html = "".join(
        f"""<div style="display:flex;justify-content:space-between;gap:12px;border-bottom:1px solid {HAIRLINE};padding:4px 0">
              <span class="mono" style="color:{INK}">{escape(w['pair'])}</span>
              <span class="mono" style="color:{PDR_RED};font-weight:600">{w['sinr']} dB</span>
            </div>"""
        for w in weak_links
    ) or f'<div style="font-size:9.5pt;color:{FAINT}">No links below the weak-link threshold.</div>'

    return f"""
    <div class="page">
      <h2 class="section"><span class="num">{num}</span>Link &amp; Topology Summary</h2>
      <div class="caption" style="margin-bottom:14px">Active parent–child links in the routing tree, ordered by SINR.</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;align-items:start">
        <table class="data">
          <thead><tr>
            <th style="text-align:left">Child</th><th style="text-align:left">Parent</th>
            <th style="text-align:right">SINR (dB)</th><th style="text-align:right">Dist (m)</th>
          </tr></thead>
          <tbody>{link_trs}</tbody>
        </table>
        <div style="display:flex;flex-direction:column;gap:12px">
          <div style="border:1px solid {HAIRLINE_STRONG};background:{SURFACE};padding:14px 16px">
            <div class="mono" style="font-size:7.5pt;letter-spacing:0.08em;text-transform:uppercase;color:{FAINT};margin-bottom:8px">Hop distribution</div>
            {hop_bars}
          </div>
          <div style="border:1px solid {HAIRLINE_STRONG};background:{SURFACE};padding:14px 16px">
            <div class="mono" style="font-size:7.5pt;letter-spacing:0.08em;text-transform:uppercase;color:{FAINT};margin-bottom:8px">Weakest links</div>
            <div style="font-size:9.5pt;color:{MUTED};line-height:1.55">{weak_html}</div>
          </div>
        </div>
      </div>
    </div>
    """


def _appendix_page(node_rows: list[dict]) -> str:
    trs = "".join(
        f"""<tr style="background:{r['bg']}">
              <td style="font-weight:600">{escape(r['id'])}</td>
              <td style="color:{MUTED}">{escape(r['role'])}</td>
              <td style="text-align:center">{escape(r['hop'])}</td>
              <td style="color:{MUTED}">{escape(r['parent'])}</td>
              <td style="text-align:right">{r['rssi']}</td>
              <td style="text-align:right">{r['sinr']}</td>
              <td style="text-align:right;font-weight:700;color:{r['pdr_color']}">{r['pdr']}</td>
              <td style="text-align:right">{r['latency']}</td>
              <td style="text-align:center;font-size:7.5pt;font-weight:600;color:{r['status_color']}">{r['status']}</td>
            </tr>"""
        for r in node_rows
    )
    return f"""
    <div class="page">
      <h2 class="section"><span class="num">A</span>Appendix — Node Link Metrics</h2>
      <div class="caption" style="margin-bottom:14px">All nodes sorted by hop count. PDR cells are colored by classification; the header row repeats on each printed page.</div>
      <table class="data">
        <thead><tr>
          <th style="text-align:left">Node ID</th><th style="text-align:left">Role</th>
          <th style="text-align:center">Hop</th><th style="text-align:left">Parent</th>
          <th style="text-align:right">RSSI (dBm)</th><th style="text-align:right">SINR (dB)</th>
          <th style="text-align:right">E2E PDR</th><th style="text-align:right">Latency (ms)</th>
          <th style="text-align:center">Status</th>
        </tr></thead>
        <tbody>{trs}</tbody>
      </table>
    </div>
    """


def build_report_html(
    project: Project,
    result: SimResult,
    generated_at: str,
    vector_png: bytes,
    threed_png: bytes,
    detail_pngs: list[tuple[list, bytes]],
    node_count: int,
    sink_count: int,
    offline_count: int,
    crowded_cluster_count: int,
    buildings_count: int,
) -> str:
    net = result.network
    net_cells = {
        "pdr": f"{net.pdr * 100:.1f}%",
        "delivered": f"{net.delivered:,}",
        "sent": f"{net.sent:,}",
        "latency": f"{net.mean_latency_ms:.0f} ms",
        "maxHops": str(net.max_hops),
        "nodeCount": str(node_count),
    }
    summary_cells = [
        ("Nodes total", str(node_count)),
        ("Sinks", str(sink_count)),
        ("Auto-promoted sinks", str(max(sink_count - 1, 0))),
        ("Events simulated", f"{net.events:,}"),
        ("Offline nodes", str(offline_count)),
        ("Active links", str(len(result.link_metrics))),
        ("Crowded clusters", str(crowded_cluster_count)),
        ("Buildings loaded", str(buildings_count)),
    ]

    sections = [_cover_section(project.name, generated_at, net_cells, summary_cells)]

    sections.append(_map_page(
        "01", "2D View — Street Map",
        f"Overview of all {node_count} nodes with mesh links, fitted to the deployment bounding box.",
        _b64_png(vector_png), legend=True,
    ))
    sections.append(_map_page(
        "02", "3D View",
        "Extruded OSM building footprints within 250 m of the deployment; links rendered above terrain.",
        _b64_png(threed_png),
    ))

    for i, (cluster, png) in enumerate(detail_pngs, start=1):
        ids = ", ".join(n.id for n in cluster)
        sections.append(_detail_page(f"{i + 2:02d}", ids, _b64_png(png)))

    sorted_links = sorted(result.link_metrics, key=lambda l: l.sinr_db, reverse=True)
    link_rows = [
        {
            "child": l.child,
            "parent": l.parent,
            "sinr": f"{l.sinr_db:.1f}",
            "dist": f"{l.distance_m:.0f}",
            "bg": SURFACE if i % 2 == 0 else "#f2f1ed",
        }
        for i, l in enumerate(sorted_links)
    ]

    hop_counts: dict[int, int] = {}
    for m in result.node_metrics:
        if m.hop is not None:
            hop_counts[m.hop] = hop_counts.get(m.hop, 0) + 1
    max_hop_count = max(hop_counts.values(), default=1)
    hop_rows = [
        {"hop": str(hop), "count": str(count), "pct": round(count / max_hop_count * 100)}
        for hop, count in sorted(hop_counts.items())
    ]

    weakest = sorted(result.link_metrics, key=lambda l: l.sinr_db)[:WEAK_LINK_COUNT]
    weak_links = [{"pair": f"{l.child} ← {l.parent}", "sinr": f"{l.sinr_db:.1f}"} for l in weakest]

    topology_num = f"{len(detail_pngs) + 3:02d}"
    sections.append(_topology_summary_page(topology_num, link_rows, hop_rows, weak_links))

    node_rows = []
    sorted_nodes = sorted(result.node_metrics, key=lambda m: (m.hop is None, m.hop or 0, m.node_id))
    for i, m in enumerate(sorted_nodes):
        status, status_color = _status(m)
        node_rows.append({
            "id": m.node_id,
            "role": m.role.upper(),
            "hop": str(m.hop) if m.hop is not None else "—",
            "parent": m.parent or "—",
            "rssi": _fmt(m.rssi_dbm),
            "sinr": _fmt(m.snr_db),
            "pdr": _fmt(m.e2e_pdr * 100 if m.e2e_pdr is not None else None, 1, "%"),
            "pdr_color": _pdr_color(m.e2e_pdr),
            "latency": _fmt(m.e2e_latency_ms),
            "status": status,
            "status_color": status_color,
            "bg": SURFACE if i % 2 == 0 else "#f2f1ed",
        })
    sections.append(_appendix_page(node_rows))

    body = "".join(sections)
    return f"<!doctype html><html><head>{HEAD}</head><body>{body}</body></html>"
