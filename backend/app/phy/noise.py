"""Thermal noise floor: kTB in dBm plus the configured receiver noise figure."""
from __future__ import annotations

from math import log10

THERMAL_NOISE_DBM_PER_HZ = -174.0


def noise_floor_dbm(bandwidth_hz: float, noise_figure_db: float) -> float:
    return THERMAL_NOISE_DBM_PER_HZ + 10.0 * log10(bandwidth_hz) + noise_figure_db
