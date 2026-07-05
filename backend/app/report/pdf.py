"""Assembles the PDF report: title/summary page, map views (2D vector, 2D
satellite, 3D, plus one zoomed detail section per crowded node cluster),
and per-node data tables (hop count, parent, RSSI, SINR, predicted PDR).
"""
from __future__ import annotations

import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .. import osm
from ..geo import LocalFrame
from ..models import Project, SimResult
from .clustering import cluster_detail_bbox, find_crowded_clusters
from .render import PADDING_PX, VIEWPORT_HEIGHT, VIEWPORT_WIDTH, MapRenderer

BUILDING_QUERY_PADDING_M = 250.0
OVERVIEW_PADDING_DEG = 0.0015

PDR_GREEN = colors.HexColor("#3d8a47")
PDR_ORANGE = colors.HexColor("#b3861c")
PDR_RED = colors.HexColor("#bb4326")
HEADER_BG = colors.HexColor("#211f1a")


def _pdr_color(pdr: float | None):
    if pdr is None:
        return colors.HexColor("#9a9587")
    if pdr >= 0.9:
        return PDR_GREEN
    if pdr >= 0.7:
        return PDR_ORANGE
    return PDR_RED


def _overview_bbox(nodes: list) -> tuple[float, float, float, float]:
    lats = [n.lat for n in nodes]
    lons = [n.lon for n in nodes]
    return (
        min(lons) - OVERVIEW_PADDING_DEG,
        min(lats) - OVERVIEW_PADDING_DEG,
        max(lons) + OVERVIEW_PADDING_DEG,
        max(lats) + OVERVIEW_PADDING_DEG,
    )


def _fmt(v, digits=1, suffix=""):
    if v is None:
        return "—"
    return f"{v:.{digits}f}{suffix}"


def generate_report_pdf(project: Project, result: SimResult) -> bytes:
    all_nodes = list(project.nodes) + [n for n in result.added_nodes if n.id not in {p.id for p in project.nodes}]
    lats = [n.lat for n in all_nodes]
    lons = [n.lon for n in all_nodes]
    frame = LocalFrame(sum(lats) / len(lats), sum(lons) / len(lons))
    overview_bbox = _overview_bbox(all_nodes)

    metrics_by_id = {m.node_id: m for m in result.node_metrics}
    roles = {m.node_id: m.role for m in result.node_metrics}
    pdr_by_node = {m.node_id: m.e2e_pdr for m in result.node_metrics}
    offline_ids = {m.node_id for m in result.node_metrics if m.offline}

    min_lon, min_lat, max_lon, max_lat = overview_bbox
    buildings = osm.fetch_buildings(
        min_lat - BUILDING_QUERY_PADDING_M / 111_000,
        min_lon - BUILDING_QUERY_PADDING_M / 111_000,
        max_lat + BUILDING_QUERY_PADDING_M / 111_000,
        max_lon + BUILDING_QUERY_PADDING_M / 111_000,
    )

    clusters = find_crowded_clusters(all_nodes, overview_bbox, frame, VIEWPORT_WIDTH, VIEWPORT_HEIGHT, PADDING_PX)

    with MapRenderer() as renderer:
        def render(bbox, mode, buildings_arg=None):
            return renderer.render(
                all_nodes, result.link_metrics, roles, pdr_by_node, offline_ids, bbox, mode,
                show_labels=True, buildings=buildings_arg,
            )

        vector_png = render(overview_bbox, "vector")
        satellite_png = render(overview_bbox, "satellite")
        threed_png = render(overview_bbox, "3d", buildings_arg=buildings)
        detail_pngs = [(cluster, render(cluster_detail_bbox(cluster), "vector")) for cluster in clusters]

    return _assemble_pdf(project, result, vector_png, satellite_png, threed_png, detail_pngs)


def _assemble_pdf(project, result: SimResult, vector_png, satellite_png, threed_png, detail_pngs) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(letter),
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
        title=f"{project.name} -- DECT NR+ Link Report",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], textColor=colors.HexColor("#211f1a"))
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=colors.HexColor("#211f1a"))
    body = styles["Normal"]

    page_w = landscape(letter)[0] - inch
    img_h = page_w * (VIEWPORT_HEIGHT / VIEWPORT_WIDTH)

    flow = []

    # --- Title / summary page ---
    flow.append(Paragraph(f"Brécilien — DECT NR+ Link Report", title_style))
    flow.append(Paragraph(f"Project: {project.name}", h2))
    flow.append(Paragraph(datetime.now(timezone.utc).strftime("Generated %Y-%m-%d %H:%M UTC"), body))
    flow.append(Spacer(1, 0.25 * inch))

    net = result.network
    sink_count = sum(1 for m in result.node_metrics if m.role == "sink")
    summary_rows = [
        ["Network PDR", f"{net.pdr * 100:.1f}%", "Mean E2E latency", f"{net.mean_latency_ms:.0f} ms"],
        ["Max hops", str(net.max_hops), "Sinks", str(sink_count)],
        ["Nodes total", str(len(result.node_metrics)), "Auto-promoted sinks", str(max(sink_count - 1, 0))],
        ["Packets delivered", f"{net.delivered:,} / {net.sent:,}", "Events simulated", f"{net.events:,}"],
    ]
    summary_table = Table(summary_rows, colWidths=[page_w * 0.22] * 4)
    summary_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c9c5b8")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f2f1ed")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f2f1ed")),
            ]
        )
    )
    flow.append(summary_table)
    flow.append(PageBreak())

    # --- Map view pages ---
    for label, png in [
        ("2D View — Street Map", vector_png),
        ("2D View — Satellite", satellite_png),
        ("3D View", threed_png),
    ]:
        flow.append(Paragraph(label, h2))
        flow.append(Spacer(1, 0.1 * inch))
        flow.append(Image(io.BytesIO(png), width=page_w, height=img_h))
        flow.append(PageBreak())

    for i, (cluster, png) in enumerate(detail_pngs, start=1):
        ids = ", ".join(n.id for n in cluster)
        flow.append(Paragraph(f"Detail Section {i} — crowded nodes: {ids}", h2))
        flow.append(Spacer(1, 0.1 * inch))
        flow.append(Image(io.BytesIO(png), width=page_w, height=img_h))
        flow.append(PageBreak())

    # --- Per-node data table ---
    flow.append(Paragraph("Node Link Metrics", h2))
    flow.append(Spacer(1, 0.1 * inch))

    header = ["Node ID", "Role", "Hop", "Parent", "RSSI (dBm)", "SINR (dB)", "E2E PDR", "Latency (ms)", "Status"]
    rows = [header]
    row_colors = []
    for m in sorted(result.node_metrics, key=lambda m: (m.hop is None, m.hop or 0, m.node_id)):
        status = "OFFLINE" if m.offline else ("SINK" if m.role == "sink" else "OK")
        rows.append(
            [
                m.node_id,
                m.role.upper(),
                str(m.hop) if m.hop is not None else "—",
                m.parent or "—",
                _fmt(m.rssi_dbm),
                _fmt(m.snr_db),
                _fmt(m.e2e_pdr * 100 if m.e2e_pdr is not None else None, 1, "%"),
                _fmt(m.e2e_latency_ms, 1),
                status,
            ]
        )
        row_colors.append(_pdr_color(m.e2e_pdr))

    table = Table(rows, repeatRows=1, colWidths=[page_w / len(header)] * len(header))
    style = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9c5b8")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
    ]
    for i, color in enumerate(row_colors, start=1):
        style.append(("TEXTCOLOR", (6, i), (6, i), color))
    table.setStyle(TableStyle(style))
    flow.append(table)

    doc.build(flow)
    return buf.getvalue()
