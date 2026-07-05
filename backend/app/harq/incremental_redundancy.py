"""HARQ Incremental Redundancy with per-process soft (mutual-information)
combining.

Each retransmission is a fresh channel use (a new fast-fading draw -- see
linklevel/fast_fading.py) carrying a different redundancy version, so the
receiver's ability to decode after n rounds depends on the *combined*
information collected so far, not just the latest round's SINR. We combine
across rounds exactly the way linklevel/effective_sinr.py combines across a
resource unit's subcarriers (both are "accumulate mutual information, stay
in the bounded MI domain" -- see that module and bler_curves.py for why):

    combined_MI(n) = mean(MI_1, ..., MI_n)

`combined_MI(n)` is then checked against the BLER curve's bler_from_mi,
whose center sits at a fixed fraction of the headroom between the code's
required rate and the modulation's hard MI cap. Each extra round can only
raise combined_MI toward (never past) that cap, which is exactly the
diminishing-returns behavior real IR-HARQ combining gain exhibits.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..linklevel.bler_curves import BlerCurve
from ..linklevel.effective_sinr import effective_mi, effective_mi_batch
from ..linklevel.fast_fading import subcarrier_power_gains, subcarrier_power_gains_batch


@dataclass(frozen=True)
class HarqOutcome:
    success: bool
    rounds_used: int


def simulate_harq(
    rng: np.random.Generator,
    *,
    model: str,
    los: bool,
    avg_sinr_linear: float,
    bits_per_symbol: int,
    num_subcarriers: int,
    subcarrier_spacing_hz: float,
    bler_curve: BlerCurve,
    max_extra_rounds: int,
) -> HarqOutcome:
    mi_history: list[float] = []
    max_rounds = max_extra_rounds + 1
    for round_idx in range(1, max_rounds + 1):
        gains = subcarrier_power_gains(
            rng, model, los, num_subcarriers, subcarrier_spacing_hz
        )
        subcarrier_sinr = avg_sinr_linear * gains
        mi_history.append(effective_mi(subcarrier_sinr, bits_per_symbol))

        combined_mi = sum(mi_history) / len(mi_history)
        bler = bler_curve.bler_from_mi(combined_mi)

        if rng.random() > bler:
            return HarqOutcome(success=True, rounds_used=round_idx)

    return HarqOutcome(success=False, rounds_used=max_rounds)


@dataclass(frozen=True)
class HarqBatchOutcome:
    successes: np.ndarray  # bool, shape (n_trials,)
    rounds_used: np.ndarray  # int, shape (n_trials,)


def simulate_harq_batch(
    rng: np.random.Generator,
    *,
    model: str,
    los: bool,
    avg_sinr_linear: float,
    bits_per_symbol: int,
    num_subcarriers: int,
    subcarrier_spacing_hz: float,
    bler_curve: BlerCurve,
    max_extra_rounds: int,
    n_trials: int,
) -> HarqBatchOutcome:
    """Same model as `simulate_harq`, run for `n_trials` independent trials
    at once. A link's Monte Carlo estimate needs thousands of trials, and
    each round's channel draw/MI/BLER computation is cheap relative to the
    per-call numpy overhead of doing it one trial at a time -- batching
    across trials amortizes that overhead the way `simulate_harq`'s
    per-trial loop can't. Unlike the sequential version, every trial draws
    a fresh channel realization for every round up to max_rounds even after
    it has already succeeded (those extra draws are simply discarded) --
    that costs a bounded, small amount of extra work per trial in exchange
    for staying vectorized, and doesn't change the outcome for any trial."""
    max_rounds = max_extra_rounds + 1
    success = np.zeros(n_trials, dtype=bool)
    rounds_used = np.full(n_trials, max_rounds, dtype=np.int64)
    pending = np.ones(n_trials, dtype=bool)
    mi_sum = np.zeros(n_trials)

    for round_idx in range(1, max_rounds + 1):
        gains = subcarrier_power_gains_batch(
            rng, model, los, num_subcarriers, subcarrier_spacing_hz, n_trials
        )
        subcarrier_sinr = avg_sinr_linear * gains
        mi_sum += effective_mi_batch(subcarrier_sinr, bits_per_symbol)
        combined_mi = mi_sum / round_idx
        bler = bler_curve.bler_from_mi_batch(combined_mi)

        round_success = rng.random(n_trials) > bler
        newly_success = pending & round_success
        success |= newly_success
        rounds_used = np.where(newly_success, round_idx, rounds_used)
        pending &= ~round_success
        if not pending.any():
            break

    return HarqBatchOutcome(successes=success, rounds_used=rounds_used)
