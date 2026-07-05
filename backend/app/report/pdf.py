"""Assembles the PDF report: title/summary page, map views (2D vector, 3D,
plus one zoomed detail section per crowded node cluster), a link/topology
summary, and a per-node data appendix. The report is built as HTML matching
the "DECT Link Report" Claude Design mock (see html_report.py) and printed to
PDF via Playwright (MapRenderer.render_pdf), reusing the same headless
Chromium instance as the map screenshots.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .. import osm
from ..geo import LocalFrame
from ..models import Project, SimResult
from .clustering import cluster_detail_bbox, find_crowded_clusters
from .html_report import build_header_footer, build_report_html
from .render import PADDING_PX, VIEWPORT_HEIGHT, VIEWPORT_WIDTH, MapRenderer

BUILDING_QUERY_PADDING_M = 250.0
OVERVIEW_PADDING_DEG = 0.0015


def _overview_bbox(nodes: list) -> tuple[float, float, float, float]:
    lats = [n.lat for n in nodes]
    lons = [n.lon for n in nodes]
    return (
        min(lons) - OVERVIEW_PADDING_DEG,
        min(lats) - OVERVIEW_PADDING_DEG,
        max(lons) + OVERVIEW_PADDING_DEG,
        max(lats) + OVERVIEW_PADDING_DEG,
    )


def generate_report_pdf(project: Project, result: SimResult) -> bytes:
    all_nodes = list(project.nodes) + [n for n in result.added_nodes if n.id not in {p.id for p in project.nodes}]
    lats = [n.lat for n in all_nodes]
    lons = [n.lon for n in all_nodes]
    frame = LocalFrame(sum(lats) / len(lats), sum(lons) / len(lons))
    overview_bbox = _overview_bbox(all_nodes)

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
        threed_png = render(overview_bbox, "3d", buildings_arg=buildings)
        detail_pngs = [(cluster, render(cluster_detail_bbox(cluster), "vector")) for cluster in clusters]

        sink_count = sum(1 for m in result.node_metrics if m.role == "sink")
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        html = build_report_html(
            project,
            result,
            generated_at,
            vector_png,
            threed_png,
            detail_pngs,
            node_count=len(result.node_metrics),
            sink_count=sink_count,
            offline_count=len(offline_ids),
            crowded_cluster_count=len(clusters),
            buildings_count=len(buildings),
        )
        header_html, footer_html = build_header_footer(project.name, generated_at)

        return renderer.render_pdf(html, header_html, footer_html)
