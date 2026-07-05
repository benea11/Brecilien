"""DECT-2020 NR MCS table (ETSI TS 103 636-3), restricted to the entries the
planner's UI exposes (MCS 0, 1, 2, 4). Each entry gives the modulation order
(bits per symbol) and the LDPC code rate, which together set both the raw
bit rate (-> transport block size / packet duration) and the required
Es/N0 operating point (-> BLER curve, see linklevel/bler_curves.py).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class McsEntry:
    mcs: int
    name: str
    bits_per_symbol: int
    code_rate: float


MCS_TABLE: dict[str, McsEntry] = {
    "0": McsEntry(mcs=0, name="BPSK 1/2", bits_per_symbol=1, code_rate=0.5),
    "1": McsEntry(mcs=1, name="QPSK 1/2", bits_per_symbol=2, code_rate=0.5),
    "2": McsEntry(mcs=2, name="QPSK 3/4", bits_per_symbol=2, code_rate=0.75),
    "4": McsEntry(mcs=4, name="16QAM 3/4", bits_per_symbol=4, code_rate=0.75),
}


def get_mcs(mcs_key: str) -> McsEntry:
    try:
        return MCS_TABLE[mcs_key]
    except KeyError as exc:
        raise ValueError(f"unsupported MCS '{mcs_key}'") from exc
