"""Per-trial frequency-selective small-scale (fast) fading.

Each Monte Carlo trial (and each HARQ round within it -- retransmissions
happen at a later time, so they see an independent fading draw, which is
exactly where HARQ's time-diversity gain comes from) draws a fresh
multipath channel realization: a handful of complex Gaussian taps on an
exponential power-delay profile, Rician-shaped for LOS links (a real
direct-path component plus scattered energy) or pure Rayleigh for NLOS. The
tap set is Fourier-transformed to a per-subcarrier frequency response so
linklevel/effective_sinr.py can combine across the resource unit the way a
real OFDM receiver's per-subcarrier SINR would vary.

The specific delay-spread constants below are representative outdoor
urban/suburban values (not a literal 3GPP CDL/TDL table lookup) -- another
documented approximation in the same spirit as the BLER curve calibration.
"""
from __future__ import annotations

import numpy as np

RMS_DELAY_SPREAD_S = {
    "uma": 300e-9,
    "umi": 150e-9,
    "logd": 200e-9,
}
LOS_RICIAN_K_DB = 10.0
NUM_TAPS = 6


def subcarrier_power_gains(
    rng: np.random.Generator,
    model: str,
    los: bool,
    num_subcarriers: int,
    subcarrier_spacing_hz: float,
) -> np.ndarray:
    """Returns a length-`num_subcarriers` array of linear power gains with
    mean 1.0 across the array (so an average-SINR link budget stays
    correct once multiplied by this array)."""
    return subcarrier_power_gains_batch(
        rng, model, los, num_subcarriers, subcarrier_spacing_hz, 1
    )[0]


def subcarrier_power_gains_batch(
    rng: np.random.Generator,
    model: str,
    los: bool,
    num_subcarriers: int,
    subcarrier_spacing_hz: float,
    n_trials: int,
) -> np.ndarray:
    """Same channel model as `subcarrier_power_gains`, but draws `n_trials`
    independent realizations at once. A Monte Carlo run needs thousands of
    these per link, and doing them one Python-level call at a time (each
    itself a handful of tiny numpy ops) makes per-call overhead dominate --
    batching amortizes that overhead across the whole trial set, which is
    what makes a large link count actually tractable.

    Returns an (n_trials, num_subcarriers) array, each row mean-normalized
    to 1.0 like the single-trial version."""
    rms_ds = RMS_DELAY_SPREAD_S.get(model, 200e-9)
    delays = np.linspace(0.0, 4.0 * rms_ds, NUM_TAPS)
    powers = np.exp(-delays / rms_ds)
    powers /= powers.sum()

    if los:
        k_lin = 10 ** (LOS_RICIAN_K_DB / 10.0)
        los_frac, nlos_frac = k_lin / (k_lin + 1.0), 1.0 / (k_lin + 1.0)
        taps = np.sqrt(powers * nlos_frac) * (
            rng.standard_normal((n_trials, NUM_TAPS)) + 1j * rng.standard_normal((n_trials, NUM_TAPS))
        ) / np.sqrt(2.0)
        taps[:, 0] += np.sqrt(powers[0] * los_frac)
    else:
        taps = np.sqrt(powers) * (
            rng.standard_normal((n_trials, NUM_TAPS)) + 1j * rng.standard_normal((n_trials, NUM_TAPS))
        ) / np.sqrt(2.0)

    k_idx = np.arange(num_subcarriers)
    phase = -2j * np.pi * np.outer(k_idx, delays) * subcarrier_spacing_hz  # (num_subcarriers, NUM_TAPS)
    h = taps @ np.exp(phase).T  # (n_trials, num_subcarriers)
    gain = np.abs(h) ** 2
    mean_gain = gain.mean(axis=1, keepdims=True)
    safe_mean = np.where(mean_gain < 1e-12, 1.0, mean_gain)
    result = gain / safe_mean
    result[mean_gain[:, 0] < 1e-12] = 1.0
    return result
