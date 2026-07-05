"""Per-MCS BLER curves, expressed as a function of *mutual information*
(bits/symbol) rather than SINR in dB.

IMPORTANT calibration note (see the plan / project notes): DECT NR+ does not
have a publicly citable, spec-extracted MCS-level BLER table available here.
These curves are *derived*, not copied from ETSI TS 103 636-3.

Why MI, not dB-SINR: linklevel/effective_sinr.py and the HARQ combiner
(harq/incremental_redundancy.py) both compute a bounded mutual-information
value per resource unit -- capped at the modulation's max of log2(M)
bits/symbol, because that's the most any modulation order can carry no
matter how good the channel is. A code's required operating point is
`R * log2(M)` bits/symbol, strictly below that cap (R < 1). Working
entirely in this bounded MI domain (rather than converting to an "effective
SINR in dB" and back) avoids a real bug we hit during calibration: a fixed
dB implementation margin, applied after converting the capped MI back to a
dB figure, could push the decision threshold *above* the maximum value the
bounded metric can ever reach for high-code-rate MCS -- which made BLER
saturate at a high floor even at arbitrarily good raw SNR. Working in MI
avoids that by construction: the margin is a fraction of the *headroom*
between the code's requirement and the hard cap, so there is always
remaining room for the waterfall to resolve down to a low BLER floor.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import log10

import numpy as np
from scipy.stats import norm

from ..phy.mcs_table import McsEntry

MARGIN_FRACTION_OF_HEADROOM = 0.35
STEEPNESS_DIVISOR_BASE = 3.0
STEEPNESS_DIVISOR_MIN = 1.5
STEEPNESS_REFERENCE_BITS = 100.0
MIN_STEEPNESS_MI = 1e-3
BLER_FLOOR = 1e-6
BLER_CEIL = 0.999


@dataclass(frozen=True)
class BlerCurve:
    center_mi: float
    steepness_mi: float
    cap_mi: float

    @property
    def center_sinr_db(self) -> float:
        """Nominal (fade-free) raw SINR that would put a single resource
        unit's mutual information exactly at this curve's decision
        threshold -- used only as the *target* for the pre-Monte-Carlo
        power-control solve, not for the per-trial BLER decision itself."""
        lin = 2.0**self.center_mi - 1.0
        return 10.0 * log10(max(lin, 1e-12))

    def bler_from_mi(self, mi: float) -> float:
        z = (mi - self.center_mi) / self.steepness_mi
        p = float(norm.sf(z))
        return min(max(p, BLER_FLOOR), BLER_CEIL)

    def bler_from_mi_batch(self, mi: np.ndarray) -> np.ndarray:
        """Batched form of `bler_from_mi` for an array of MI values."""
        z = (mi - self.center_mi) / self.steepness_mi
        return np.clip(norm.sf(z), BLER_FLOOR, BLER_CEIL)

    def neg_log_pdr_from_mi(self, mi: float) -> float:
        """-log(estimated single-round success probability), *without*
        bler_from_mi's BLER_CEIL clip.

        This exists for routing (see sim/topology.py), not the Monte Carlo
        BLER decision -- clipping BLER to a ceiling is right for the
        simulation (a real trial's outcome is a coin flip, not "how bad"),
        but it's wrong for a routing *cost*: two links that are both way
        outside range clip to the exact same BLER_CEIL and therefore the
        exact same cost, even though one might be dramatically worse than
        the other. That makes every sufficiently-bad edge in the graph
        look identical, so a path through several free hops plus one bad
        one comes out as an exact tie with one bad hop alone instead of a
        clear win -- which is what was producing a pure star even where a
        real relay chain existed. `norm.logsf` stays accurate (no
        underflow-to-zero) far into the tail, so this keeps differentiating
        "bad" from "much worse" instead of flattening them together."""
        z = (mi - self.center_mi) / self.steepness_mi
        return float(-norm.logsf(-z))


def build_bler_curve(mcs: McsEntry, coded_block_bits: int) -> BlerCurve:
    cap_mi = float(mcs.bits_per_symbol)
    required_mi = mcs.bits_per_symbol * mcs.code_rate
    headroom = max(cap_mi - required_mi, 1e-6)

    center_mi = required_mi + MARGIN_FRACTION_OF_HEADROOM * headroom
    remaining = cap_mi - center_mi

    divisor = max(
        STEEPNESS_DIVISOR_BASE * (max(coded_block_bits, 1) / STEEPNESS_REFERENCE_BITS) ** 0.5,
        STEEPNESS_DIVISOR_MIN,
    )
    steepness_mi = max(remaining / divisor, MIN_STEEPNESS_MI)
    return BlerCurve(center_mi=center_mi, steepness_mi=steepness_mi, cap_mi=cap_mi)
