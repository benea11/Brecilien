"""3GPP TR 38.901 sec. 7.4.3 outdoor-to-indoor building penetration loss,
applied when a LEAF node's position falls inside a building footprint (the
UI's "Building entry loss (O2I, OSM footprints)" toggle) -- i.e. the node
represents equipment mounted just inside an exterior wall/window, reached
from an outdoor infrastructure radio.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import log10

DEFAULT_INDOOR_DEPTH_M = 10.0
INDOOR_LOSS_DB_PER_M = 0.5


@dataclass(frozen=True)
class O2iResult:
    penetration_loss_db: float
    indoor_loss_db: float

    @property
    def total_db(self) -> float:
        return self.penetration_loss_db + self.indoor_loss_db


def low_loss_penetration_db(fc_hz: float) -> float:
    fc_ghz = fc_hz / 1e9
    l_glass = 2.0 + 0.2 * fc_ghz
    l_concrete = 5.0 + 4.0 * fc_ghz
    return -10.0 * log10(0.3 * 10 ** (-l_glass / 10.0) + 0.7 * 10 ** (-l_concrete / 10.0))


def high_loss_penetration_db(fc_hz: float) -> float:
    fc_ghz = fc_hz / 1e9
    l_irr_glass = 23.0 + 0.3 * fc_ghz
    l_concrete = 5.0 + 4.0 * fc_ghz
    return -10.0 * log10(
        0.7 * 10 ** (-l_irr_glass / 10.0) + 0.3 * 10 ** (-l_concrete / 10.0)
    )


def o2i_loss(fc_hz: float, high_loss: bool = False, indoor_depth_m: float = DEFAULT_INDOOR_DEPTH_M) -> O2iResult:
    penetration = high_loss_penetration_db(fc_hz) if high_loss else low_loss_penetration_db(fc_hz)
    return O2iResult(
        penetration_loss_db=penetration,
        indoor_loss_db=INDOOR_LOSS_DB_PER_M * indoor_depth_m,
    )
