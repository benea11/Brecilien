"""Deterministic LOS/NLOS classification from real building footprints, via
3D ray-vs-building intersection rather than TR 38.901's statistical LOS
probability formula.

The direct TX-RX line is projected into local ENU meters (see app/geo.py).
For every building footprint whose 2D outline the horizontal projection of
that line crosses, we check whether the straight-line height at the crossing
is below the building's height (flat-roof assumption); if so, the link is
NLOS and the crossing becomes a rooftop-diffraction obstruction for
propagation/diffraction.py. Buildings the line simply doesn't cross are
irrelevant, LOS-wise, no matter how tall.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil

from shapely.geometry import LineString, Point

from ..geo import LocalFrame
from .building_index import BuildingIndex

# A line query's STRtree candidates are filtered by its *bounding box*, not
# its actual path -- for a long link that runs diagonally across the
# project area, that bbox can cover most of the index even though the line
# itself only grazes a handful of buildings (a multi-city CSV import can
# make this the dominant cost of every link budget: one query returning
# hundreds of thousands of candidates for what's actually a ~60 m wide
# corridor). Chunking the query into short segments keeps each one's bbox
# tight to the segment regardless of the link's total length.
LOS_QUERY_CHUNK_M = 500.0


def _candidate_indices(line: LineString, index: BuildingIndex) -> set[int]:
    if line.length <= LOS_QUERY_CHUNK_M:
        return set(index.tree.query(line, predicate="intersects"))
    n_chunks = ceil(line.length / LOS_QUERY_CHUNK_M)
    (x0, y0), (x1, y1) = line.coords
    candidates: set[int] = set()
    for i in range(n_chunks):
        t0, t1 = i / n_chunks, (i + 1) / n_chunks
        seg = LineString(
            [(x0 + (x1 - x0) * t0, y0 + (y1 - y0) * t0), (x0 + (x1 - x0) * t1, y0 + (y1 - y0) * t1)]
        )
        candidates.update(index.tree.query(seg, predicate="intersects"))
    return candidates


@dataclass(frozen=True)
class Obstruction:
    building_id: str
    distance_along_path_m: float  # 0 = at tx, path_length_m = at rx
    height_m: float


@dataclass(frozen=True)
class LosResult:
    los: bool
    path_length_m: float
    obstructions: list[Obstruction] = field(default_factory=list)


def _line_height(h_tx: float, h_rx: float, t: float) -> float:
    return h_tx + (h_rx - h_tx) * t


def check_los(
    frame: LocalFrame,
    tx_lat: float,
    tx_lon: float,
    tx_h: float,
    rx_lat: float,
    rx_lon: float,
    rx_h: float,
    index: BuildingIndex,
) -> LosResult:
    tx_xy = frame.to_xy(tx_lat, tx_lon)
    rx_xy = frame.to_xy(rx_lat, rx_lon)
    line = LineString([tx_xy, rx_xy])
    path_length_m = line.length

    if path_length_m < 1e-6:
        return LosResult(los=True, path_length_m=0.0)

    tx_pt = Point(tx_xy)
    rx_pt = Point(rx_xy)

    obstructions: list[Obstruction] = []
    for i in _candidate_indices(line, index):
        poly = index.polygons[i]
        # _candidate_indices already filtered to real (predicate=
        # "intersects") matches, not just bounding-box overlaps, so no need
        # to re-check line.intersects(poly) here.
        if poly.contains(tx_pt) or poly.contains(rx_pt):
            # A node whose position falls inside a footprint is mounted to
            # that building's exterior (wall/roof), never embedded within
            # it -- see propagation/o2i.py. So its own host building must
            # not become a rooftop-diffraction obstruction on this link;
            # that would double-penalize the link (diffraction loss for
            # supposedly clearing its own roof, on top of o2i wall-
            # penetration loss) for a building the signal doesn't actually
            # need to go over.
            continue
        clipped = line.intersection(poly)
        if clipped.is_empty:
            continue
        height_m = index.heights[i]
        building_id = index.ids[i]
        segments = list(clipped.geoms) if hasattr(clipped, "geoms") else [clipped]
        for seg in segments:
            coords = list(seg.coords)
            if len(coords) < 2:
                continue
            # project the two segment endpoints back onto the original line
            t_start = line.project(Point(coords[0]), normalized=True)
            t_end = line.project(Point(coords[-1]), normalized=True)
            t_mid = (t_start + t_end) / 2.0
            line_h_start = _line_height(tx_h, rx_h, t_start)
            line_h_end = _line_height(tx_h, rx_h, t_end)
            if min(line_h_start, line_h_end) < height_m:
                obstructions.append(
                    Obstruction(
                        building_id=building_id,
                        distance_along_path_m=t_mid * path_length_m,
                        height_m=height_m,
                    )
                )

    obstructions.sort(key=lambda o: o.distance_along_path_m)
    return LosResult(los=len(obstructions) == 0, path_length_m=path_length_m, obstructions=obstructions)
