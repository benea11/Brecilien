"""Effective-SINR mapping (MIESM-proxy): collapse a resource unit's
per-subcarrier SINR values into a single mutual-information figure that
predicts BLER as accurately as the frequency-selective channel allows.

True MIESM uses per-modulation bit-interleaved-coded-modulation mutual
information curves from link-level simulation campaigns. Lacking a citable
DECT NR+ BICM table, we use the capacity-based proxy common in system-level
simulators when such tables aren't available: per-subcarrier Shannon mutual
information capped at the modulation's max (log2(M) bits/symbol), averaged
across the resource unit. This preserves MIESM's key property -- a resource
unit with a few very poor subcarriers and many good ones is scored worse
than the plain average SINR would suggest, because capacity saturates for
the good subcarriers but craters for the poor ones.

The result is intentionally left in the bounded MI domain (bits/symbol,
0..log2(M)) rather than converted to an "effective SINR in dB" -- see
bler_curves.py's module docstring for why that round-trip is a footgun.
"""
from __future__ import annotations

import numpy as np


def effective_mi(subcarrier_sinr_linear: np.ndarray, bits_per_symbol: int) -> float:
    cap = float(bits_per_symbol)
    mi = np.minimum(np.log2(1.0 + np.maximum(subcarrier_sinr_linear, 1e-12)), cap)
    return float(mi.mean())


def effective_mi_batch(subcarrier_sinr_linear: np.ndarray, bits_per_symbol: int) -> np.ndarray:
    """Batched form of `effective_mi`: takes an (n_trials, num_subcarriers)
    array and returns one MI value per trial (row)."""
    cap = float(bits_per_symbol)
    mi = np.minimum(np.log2(1.0 + np.maximum(subcarrier_sinr_linear, 1e-12)), cap)
    return mi.mean(axis=-1)
