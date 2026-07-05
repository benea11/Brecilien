"""A spatial index over a project's building footprints (projected into the
local ENU frame once), so LOS checks and the coverage-heatmap grid -- which
between them issue thousands of building-intersection queries per
simulate() call -- don't each re-project and brute-force scan every
building in the bounding box."""
from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import Polygon
from shapely.strtree import STRtree

from ..geo import LocalFrame
from ..models import Building


@dataclass
class BuildingIndex:
    ids: list[str]
    heights: list[float]
    polygons: list[Polygon]
    tree: STRtree


def build_index(frame: LocalFrame, buildings: list[Building]) -> BuildingIndex:
    ids: list[str] = []
    heights: list[float] = []
    polys: list[Polygon] = []
    for b in buildings:
        ring_xy = [frame.to_xy(lat, lon) for lon, lat in b.footprint]
        if len(ring_xy) < 4:
            continue
        poly = Polygon(ring_xy)
        if not poly.is_valid:
            continue
        ids.append(b.id)
        heights.append(b.height_m)
        polys.append(poly)
    return BuildingIndex(ids=ids, heights=heights, polygons=polys, tree=STRtree(polys))
