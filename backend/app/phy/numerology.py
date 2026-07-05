"""DECT-2020 NR PHY numerology (ETSI TS 103 636-3 clause 5).

DECT NR+ keeps subcarrier spacing fixed at 27 kHz and scales the FFT size
(hence occupied bandwidth) with the numerology factor mu in {1, 2, 4, 8, 16}:

    occupied_bandwidth_hz = mu * 1_728_000   (mu=1 -> 1.728 MHz, matching the
                                               UI's "SUBCARRIER mu" dropdown)
    fft_size(mu)          = 64 * mu
    subcarrier_spacing_hz = 27_000            (constant across mu)

Frame/slot timing: a 10 ms frame carries 24 slots (416.67 us/slot); we take
10 OFDM symbols per slot, which is the DECT NR+ slot structure used for both
the traffic packet-duration calculation and the numerology's contribution to
the effective-SINR resource-unit bandwidth. This is a simplification of the
full symbol/cyclic-prefix accounting in the spec's Annex, but it is applied
uniformly across all configurations, so relative comparisons between MCS/mu
choices -- which is what this planner is for -- stay meaningful.
"""
from __future__ import annotations

from dataclasses import dataclass

BASE_BANDWIDTH_HZ = 1_728_000.0
SUBCARRIER_SPACING_HZ = 27_000.0
BASE_FFT_SIZE = 64
SLOTS_PER_FRAME = 24
FRAME_DURATION_S = 10e-3
SYMBOLS_PER_SLOT = 10


@dataclass(frozen=True)
class Numerology:
    mu: int
    bandwidth_hz: float
    fft_size: int
    subcarrier_spacing_hz: float
    slot_duration_s: float
    symbol_duration_s: float

    @property
    def slots_per_second(self) -> float:
        return 1.0 / self.slot_duration_s


def get_numerology(mu: int) -> Numerology:
    if mu not in (1, 2, 4, 8, 16):
        raise ValueError(f"invalid DECT NR+ numerology mu={mu}")
    slot_duration = FRAME_DURATION_S / SLOTS_PER_FRAME
    return Numerology(
        mu=mu,
        bandwidth_hz=mu * BASE_BANDWIDTH_HZ,
        fft_size=mu * BASE_FFT_SIZE,
        subcarrier_spacing_hz=SUBCARRIER_SPACING_HZ,
        slot_duration_s=slot_duration,
        symbol_duration_s=slot_duration / SYMBOLS_PER_SLOT,
    )
