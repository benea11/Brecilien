"""Finds groups of nodes packed too tightly for their ID labels to stay
legible in the report's overview map, so the PDF can add a zoomed-in
"detail" section for each such group instead of a single overview where
labels clip over each other.
"""
from __future__ import annotations

from ..geo import LocalFrame
from ..models import Node

Bbox = tuple[float, float, float, float]

# Rough on-screen footprint of one node's marker + ID label (see
# map_render.html's .node-text / .node-shape) -- two nodes closer than this
# on the rendered overview will have overlapping labels.
LABEL_FOOTPRINT_PX = 55.0
DETAIL_PADDING_FACTOR = 0.6  # extra margin around a cluster's own extent


def _bbox_span_m(bbox: Bbox, frame: LocalFrame) -> tuple[float, float]:
    min_lon, min_lat, max_lon, max_lat = bbox
    x0, y0 = frame.to_xy(min_lat, min_lon)
    x1, y1 = frame.to_xy(max_lat, max_lon)
    return abs(x1 - x0), abs(y1 - y0)


def _meters_per_pixel(bbox: Bbox, frame: LocalFrame, viewport_w: int, viewport_h: int, padding_px: int) -> float:
    span_x_m, span_y_m = _bbox_span_m(bbox, frame)
    usable_w = max(viewport_w - 2 * padding_px, 1)
    usable_h = max(viewport_h - 2 * padding_px, 1)
    # fitBounds ends up constrained by whichever axis needs more px/m --
    # take the larger of the two so the threshold matches the actual
    # rendered scale, not an optimistic one.
    return max(span_x_m / usable_w, span_y_m / usable_h)


def find_crowded_clusters(
    nodes: list[Node],
    overview_bbox: Bbox,
    frame: LocalFrame,
    viewport_w: int,
    viewport_h: int,
    padding_px: int,
) -> list[list[Node]]:
    """Union-find over pairwise distance < LABEL_FOOTPRINT_PX (converted to
    meters at the overview's actual rendered scale). Returns only groups of
    2+ nodes -- an isolated node is never "crowded" with itself."""
    if len(nodes) < 2:
        return []

    m_per_px = _meters_per_pixel(overview_bbox, frame, viewport_w, viewport_h, padding_px)
    threshold_m = LABEL_FOOTPRINT_PX * m_per_px

    n = len(nodes)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    coords = [frame.to_xy(node.lat, node.lon) for node in nodes]
    for i in range(n):
        xi, yi = coords[i]
        for j in range(i + 1, n):
            xj, yj = coords[j]
            if ((xi - xj) ** 2 + (yi - yj) ** 2) ** 0.5 < threshold_m:
                union(i, j)

    groups: dict[int, list[Node]] = {}
    for i, node in enumerate(nodes):
        groups.setdefault(find(i), []).append(node)

    return [g for g in groups.values() if len(g) >= 2]


def cluster_detail_bbox(cluster: list[Node]) -> Bbox:
    """A tight bbox around one crowded cluster, padded so its own markers
    aren't flush against the detail view's edges."""
    lats = [n.lat for n in cluster]
    lons = [n.lon for n in cluster]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)
    lat_pad = max((max_lat - min_lat) * DETAIL_PADDING_FACTOR, 0.0015)
    lon_pad = max((max_lon - min_lon) * DETAIL_PADDING_FACTOR, 0.0015)
    return (min_lon - lon_pad, min_lat - lat_pad, max_lon + lon_pad, max_lat + lat_pad)
