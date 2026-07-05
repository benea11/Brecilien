"""Transport-block-size / packet-duration calculation.

DECT NR+'s exact resource-element/PCC-quantized TBS tables (ETSI TS 103
636-3 Annex) aren't reproduced here verbatim. Instead we compute an
occupied-bandwidth-consistent raw bit rate from the numerology + MCS and
round up to whole slots -- adequate for latency/throughput comparisons
across configurations, which is what this planner is for. See the module
docstring in phy/numerology.py for the same caveat on symbol timing.

A fixed PHY/MAC header overhead (5 bytes) is added to the application
payload before computing slot count, and a guard-band fraction removes the
outermost subcarriers of the FFT from the usable data allocation.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from .mcs_table import McsEntry
from .numerology import Numerology, SYMBOLS_PER_SLOT

HEADER_BYTES = 5
GUARD_BAND_FRACTION = 0.15  # outermost subcarriers reserved as guard band


@dataclass(frozen=True)
class PacketTiming:
    slots_needed: int
    packet_duration_s: float
    raw_bits_per_slot: float


def data_subcarriers(num: Numerology) -> int:
    return max(1, int(round(num.fft_size * (1 - GUARD_BAND_FRACTION))))


def packet_timing(payload_bytes: int, mcs: McsEntry, num: Numerology) -> PacketTiming:
    total_bits = (payload_bytes + HEADER_BYTES) * 8
    bits_per_slot = (
        data_subcarriers(num) * SYMBOLS_PER_SLOT * mcs.bits_per_symbol * mcs.code_rate
    )
    slots_needed = max(1, ceil(total_bits / bits_per_slot))
    return PacketTiming(
        slots_needed=slots_needed,
        packet_duration_s=slots_needed * num.slot_duration_s,
        raw_bits_per_slot=bits_per_slot,
    )
