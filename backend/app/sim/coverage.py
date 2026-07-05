"""Coverage heatmap grid: for each cell, the best RSSI any infrastructure
node (sink/relay) could deliver there if transmitting at the project's
power budget ceiling. This mirrors the mockup's heatmap layer, but every
cell now goes through the same TR 38.901 + real-geometry LOS/diffraction
pipeline as the node-to-node link budgets, via propagation/link_budget.py,
instead of a closed-form distance formula.
"""
from __future__ import annotations

from ..geo import LocalFrame, horizontal_distance_m
from ..models import CoveragePoint, Node, Params
from ..phy.antenna import AntennaSpec
from ..propagation.building_index import BuildingIndex
from ..propagation.link_budget import compute_link_budget
from ..propagation.shadow_field import ShadowField

GRID_RECEIVER_HEIGHT_M = 1.5
GRID_CELL_M = 45.0
GRID_MIN_RSSI_DBM = -105.0
GRID_PADDING_M = 300.0

# Now that sim/topology.py lets any node become a relay (see its module
# docstring), a large project can have dozens/hundreds of infra nodes
# instead of just one sink -- evaluating every one of them, full physics
# and all, against every grid cell (grid_cells x infra_count real
# link-budget calls) is the product of two numbers that both grew. Only
# the nearest few infra nodes to a given cell can plausibly deliver its
# best RSSI (path loss only gets worse with distance, and diffraction/O2I
# only ever subtracts more), so pre-filtering by plain physical distance
# -- which is nearly free compared to a real link-budget call -- to just
# those candidates before running the expensive geometry doesn't discard
# any cell's true best source, only the ones with no chance of winning.
MAX_COVERAGE_SOURCES_PER_CELL = 4

# Relays can now be scattered across a project's whole extent (again, see
# sim/topology.py), so the padded bbox around every infra node -- and
# therefore the raw cell count at a fixed 45 m resolution -- scales with
# deployment size, not just node count: a 50 km-wide import would demand
# a million-plus-cell grid at GRID_CELL_M. Capping cells-per-axis keeps
# the heatmap's total size bounded by coarsening resolution only when the
# project is actually that large; a normal few-km project still gets the
# full 45 m grid untouched.
MAX_GRID_CELLS_PER_AXIS = 150


def compute_coverage_grid(
    nodes: list[Node],
    roles: dict[str, str],
    params: Params,
    fc_hz: float,
    frame: LocalFrame,
    bbox: tuple[float, float, float, float],
    building_index: BuildingIndex,
    shadow_field: ShadowField,
    antenna: AntennaSpec,
    cell_m: float = GRID_CELL_M,
) -> list[CoveragePoint]:
    infra = [n for n in nodes if roles[n.id] != "leaf"]
    if not infra:
        return []

    min_lat, min_lon, max_lat, max_lon = bbox
    min_x, min_y = frame.to_xy(min_lat, min_lon)
    max_x, max_y = frame.to_xy(max_lat, max_lon)
    cell_m = max(cell_m, (max_x - min_x) / MAX_GRID_CELLS_PER_AXIS, (max_y - min_y) / MAX_GRID_CELLS_PER_AXIS)

    points: list[CoveragePoint] = []
    x = min_x
    while x < max_x:
        y = min_y
        while y < max_y:
            lat, lon = frame.from_xy(x + cell_m / 2.0, y + cell_m / 2.0)
            receiver = Node(id="__grid__", lon=lon, lat=lat, h=GRID_RECEIVER_HEIGHT_M)
            candidates = infra
            if len(infra) > MAX_COVERAGE_SOURCES_PER_CELL:
                candidates = sorted(
                    infra, key=lambda tx: horizontal_distance_m(tx.lat, tx.lon, lat, lon)
                )[:MAX_COVERAGE_SOURCES_PER_CELL]
            best_rssi = None
            for tx in candidates:
                budget = compute_link_budget(
                    tx,
                    receiver,
                    model=params.model,
                    fc_hz=fc_hz,
                    sigma_db=params.sigma,
                    o2i_enabled=False,
                    rx_is_leaf=False,
                    frame=frame,
                    building_index=building_index,
                    shadow_field=shadow_field,
                    antenna=antenna,
                )
                rssi = params.max_tx_power_dbm + budget.antenna_gain_db - (
                    budget.pathloss_db + budget.diffraction_loss_db + budget.shadow_db
                )
                if best_rssi is None or rssi > best_rssi:
                    best_rssi = rssi
            if best_rssi is not None and best_rssi >= GRID_MIN_RSSI_DBM:
                points.append(CoveragePoint(lat=lat, lon=lon, rssi_dbm=best_rssi))
            y += cell_m
        x += cell_m
    return points
