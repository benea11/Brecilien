"""Composes the propagation sub-models (TR 38.901 pathloss, real-geometry
LOS/NLOS, rooftop diffraction, O2I, antenna pattern, correlated shadowing)
into one large-scale link budget for a TX/RX node pair. This is the single
place that combines "everything except transmit power and fast fading" so
sim/topology.py (comparing candidate parents), sim/engine.py (solving
transmit power, then running the Monte Carlo) and the coverage-grid
computation stay consistent.
"""
from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import Point

from ..geo import LocalFrame, horizontal_distance_m
from ..models import Node
from ..phy.antenna import AntennaSpec, link_antenna_gain_db
from . import o2i as o2i_mod
from .building_index import BuildingIndex
from .diffraction import excess_diffraction_loss_db
from .los import LosResult, check_los
from .shadow_field import ShadowField
from .tr38901 import pathloss


@dataclass(frozen=True)
class LinkBudget:
    distance_m: float
    los: bool
    pathloss_db: float
    diffraction_loss_db: float
    o2i_loss_db: float
    antenna_gain_db: float
    shadow_db: float

    @property
    def large_scale_loss_db(self) -> float:
        """Total loss excluding tx power and fast fading; lower is better."""
        return (
            self.pathloss_db
            + self.diffraction_loss_db
            + self.o2i_loss_db
            + self.shadow_db
            - self.antenna_gain_db
        )


def point_in_any_building(lat: float, lon: float, frame: LocalFrame, index: BuildingIndex) -> bool:
    pt = Point(*frame.to_xy(lat, lon))
    return len(index.tree.query(pt, predicate="contains")) > 0


def compute_link_budget(
    tx: Node,
    rx: Node,
    *,
    model: str,
    fc_hz: float,
    sigma_db: float,
    o2i_enabled: bool,
    rx_is_leaf: bool,
    frame: LocalFrame,
    building_index: BuildingIndex,
    shadow_field: ShadowField,
    antenna: AntennaSpec,
) -> LinkBudget:
    d2d_m = horizontal_distance_m(tx.lat, tx.lon, rx.lat, rx.lon)
    los_result: LosResult = check_los(
        frame, tx.lat, tx.lon, tx.h, rx.lat, rx.lon, rx.h, building_index
    )
    pl = pathloss(model, d2d_m, tx.h, rx.h, fc_hz, los_result.los)

    diffraction_db = 0.0
    if not los_result.los:
        diffraction_db = excess_diffraction_loss_db(
            los_result.path_length_m, tx.h, rx.h, los_result.obstructions, fc_hz
        )

    o2i_db = 0.0
    if o2i_enabled and rx_is_leaf and point_in_any_building(rx.lat, rx.lon, frame, building_index):
        o2i_db = o2i_mod.o2i_loss(fc_hz).total_db

    antenna_gain_db = link_antenna_gain_db(antenna, tx.h, rx.h, max(d2d_m, 1.0))
    shadow_sample = shadow_field.sample(rx.lat, rx.lon, los_result.los)
    shadow_db = shadow_sample * sigma_db

    return LinkBudget(
        distance_m=d2d_m,
        los=los_result.los,
        pathloss_db=pl.pathloss_db,
        diffraction_loss_db=diffraction_db,
        o2i_loss_db=o2i_db,
        antenna_gain_db=antenna_gain_db,
        shadow_db=shadow_db,
    )
