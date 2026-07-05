"""3GPP TR 38.901 UMa / UMi-Street-Canyon pathloss (Table 7.4.1-1), plus a
plain log-distance fallback matching the mockup's third dropdown entry.

TR 38.901's UMa/UMi formulas were calibrated and validated down to ~2 GHz
(the "0.5-100 GHz" scope was added in a later revision covering the general
shape, not a re-validation of the low-frequency coefficients). DECT NR+ runs
at 902 MHz or 1.9 GHz, both below that floor, so the frequency-dependent
`20*log10(fc_GHz)` / `21.3*log10(fc_GHz)` terms use fc clamped to >= 2 GHz.
This is a deliberate, documented extrapolation-avoidance choice: it slightly
*overestimates* pathloss relative to naively plugging in sub-2GHz values
(which would predict less loss than the model was ever shown to hold for),
which is the conservative direction to err in for a planning tool.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import log10

C_M_PER_S = 299_792_458.0
FC_CLAMP_FLOOR_GHZ = 2.0
UMA_EFFECTIVE_ENV_HEIGHT_M = 1.0
UMI_EFFECTIVE_ENV_HEIGHT_M = 1.0


@dataclass(frozen=True)
class PathlossResult:
    pathloss_db: float
    shadow_sigma_db: float
    los: bool  # echoes the input LOS state, for downstream bookkeeping


def _fc_term_ghz(fc_hz: float) -> float:
    return max(fc_hz / 1e9, FC_CLAMP_FLOOR_GHZ)


def _breakpoint_distance_m(fc_hz: float, h_bs: float, h_ut: float, h_e: float) -> float:
    h_bs_eff = max(h_bs - h_e, 1e-3)
    h_ut_eff = max(h_ut - h_e, 1e-3)
    return 4.0 * h_bs_eff * h_ut_eff * fc_hz / C_M_PER_S


def uma_pathloss(
    d2d_m: float, h_bs: float, h_ut: float, fc_hz: float, los: bool
) -> PathlossResult:
    d2d_m = max(d2d_m, 10.0)
    d3d_m = (d2d_m**2 + (h_bs - h_ut) ** 2) ** 0.5
    fc_ghz = _fc_term_ghz(fc_hz)
    d_bp = _breakpoint_distance_m(fc_hz, h_bs, h_ut, UMA_EFFECTIVE_ENV_HEIGHT_M)

    if d2d_m <= d_bp:
        pl_los = 28.0 + 22.0 * log10(d3d_m) + 20.0 * log10(fc_ghz)
    else:
        pl_los = (
            28.0
            + 40.0 * log10(d3d_m)
            + 20.0 * log10(fc_ghz)
            - 9.0 * log10(d_bp**2 + (h_bs - h_ut) ** 2)
        )

    if los:
        return PathlossResult(pathloss_db=pl_los, shadow_sigma_db=4.0, los=True)

    pl_nlos = (
        13.54
        + 39.08 * log10(d3d_m)
        + 20.0 * log10(fc_ghz)
        - 0.6 * (h_ut - 1.5)
    )
    return PathlossResult(
        pathloss_db=max(pl_los, pl_nlos), shadow_sigma_db=6.0, los=False
    )


def umi_pathloss(
    d2d_m: float, h_bs: float, h_ut: float, fc_hz: float, los: bool
) -> PathlossResult:
    d2d_m = max(d2d_m, 10.0)
    d3d_m = (d2d_m**2 + (h_bs - h_ut) ** 2) ** 0.5
    fc_ghz = _fc_term_ghz(fc_hz)
    d_bp = _breakpoint_distance_m(fc_hz, h_bs, h_ut, UMI_EFFECTIVE_ENV_HEIGHT_M)

    if d2d_m <= d_bp:
        pl_los = 32.4 + 21.0 * log10(d3d_m) + 20.0 * log10(fc_ghz)
    else:
        pl_los = (
            32.4
            + 40.0 * log10(d3d_m)
            + 20.0 * log10(fc_ghz)
            - 9.5 * log10(d_bp**2 + (h_bs - h_ut) ** 2)
        )

    if los:
        return PathlossResult(pathloss_db=pl_los, shadow_sigma_db=4.0, los=True)

    pl_nlos = (
        35.3 * log10(d3d_m)
        + 22.4
        + 21.3 * log10(fc_ghz)
        - 0.3 * (h_ut - 1.5)
    )
    return PathlossResult(
        pathloss_db=max(pl_los, pl_nlos), shadow_sigma_db=7.82, los=False
    )


def log_distance_pathloss(
    d2d_m: float, h_bs: float, h_ut: float, fc_hz: float, los: bool, path_loss_exponent: float = 3.2
) -> PathlossResult:
    """Simple single-slope log-distance model, free-space referenced at 1 m,
    for parity with the mockup's `LogDistancePropagationLossModel` option."""
    d2d_m = max(d2d_m, 10.0)
    d3d_m = (d2d_m**2 + (h_bs - h_ut) ** 2) ** 0.5
    fc_ghz = _fc_term_ghz(fc_hz)
    pl0 = 32.4 + 20.0 * log10(fc_ghz)  # free-space loss at 1 m reference
    n = 2.2 if los else path_loss_exponent
    pl = pl0 + 10.0 * n * log10(d3d_m)
    return PathlossResult(pathloss_db=pl, shadow_sigma_db=4.0 if los else 6.0, los=los)


def pathloss(
    model: str, d2d_m: float, h_bs: float, h_ut: float, fc_hz: float, los: bool
) -> PathlossResult:
    if model == "uma":
        return uma_pathloss(d2d_m, h_bs, h_ut, fc_hz, los)
    if model == "umi":
        return umi_pathloss(d2d_m, h_bs, h_ut, fc_hz, los)
    if model == "logd":
        return log_distance_pathloss(d2d_m, h_bs, h_ut, fc_hz, los)
    raise ValueError(f"unknown propagation model '{model}'")
