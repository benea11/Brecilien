"""Local ENU (east-north-up) projection helpers.

All propagation/geometry math operates in flat local meters rather than
lat/lon degrees. We project around a fixed origin (the project's first
sink, or the topology centroid) using an equirectangular approximation --
accurate to well under 1% error over the few-kilometer spans this planner
targets, and far cheaper than a full geodesic library for the O(n^2) link
and heatmap-grid computations the simulation engine runs per request.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians, sqrt

EARTH_R_LAT_M = 110_540.0  # meters per degree latitude (~constant)
EARTH_R_LON_M = 111_320.0  # meters per degree longitude at the equator


@dataclass(frozen=True)
class LocalFrame:
    """Equirectangular local-tangent-plane frame anchored at (lat0, lon0)."""

    lat0: float
    lon0: float

    @property
    def _k(self) -> float:
        return cos(radians(self.lat0))

    def to_xy(self, lat: float, lon: float) -> tuple[float, float]:
        """Returns (east_m, north_m) relative to the frame origin."""
        x = (lon - self.lon0) * EARTH_R_LON_M * self._k
        y = (lat - self.lat0) * EARTH_R_LAT_M
        return x, y

    def from_xy(self, x: float, y: float) -> tuple[float, float]:
        """Returns (lat, lon) for a given (east_m, north_m) offset."""
        lon = self.lon0 + x / (EARTH_R_LON_M * self._k)
        lat = self.lat0 + y / EARTH_R_LAT_M
        return lat, lon


def horizontal_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    k = cos(radians((lat1 + lat2) / 2.0))
    dx = (lon2 - lon1) * EARTH_R_LON_M * k
    dy = (lat2 - lat1) * EARTH_R_LAT_M
    return sqrt(dx * dx + dy * dy)
