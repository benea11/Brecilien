"""ITU-R P.526 multiple knife-edge diffraction (Deygout method) -- the
concrete "attenuation loss of the buildings" term that is added on top of
TR 38.901's statistical NLOS pathloss regression whenever propagation/los.py
finds the direct path physically crosses one or more rooftops.

Deygout's method: find the obstruction with the largest Fresnel diffraction
parameter v (the "main edge"), add its single-knife-edge loss, then
recurse on the sub-paths either side of it (tx -> main edge, main edge ->
rx) for any remaining obstructions in each half. This is the standard way
to extend single-knife-edge diffraction (ITU-R P.526 sec. 4.2-4.3) to
multiple obstructions without the pessimism of just summing every edge's
loss independently.

Two guardrails keep this physical for real OSM data, where a low leaf node
a few hundred meters away can nominally "cross" dozens of adjacent
building footprints along a street:

1. Only the `MAX_DOMINANT_EDGES` most significant obstructions (by their
   individual Fresnel parameter against the direct path) are fed into
   Deygout. ITU-R's multiple-edge guidance is calibrated for a handful of
   dominant screens, not dozens of closely-spaced party walls -- a link
   embedded at street level among many adjacent low buildings is a street-
   canyon multipath scenario (already captured by the UMi/UMa NLOS
   statistical regression), not a rooftop-diffraction scenario, so we don't
   let minor edges pile on indefinitely.
2. The total is capped at `MAX_DIFFRACTION_LOSS_DB`: this term represents
   "worse than the statistical NLOS average because of an identifiable
   blocking structure," which should be a bounded correction, not an
   unbounded one -- the NLOS regression already carries tens of dB of
   average clutter loss on its own.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import log10, sqrt

from .los import Obstruction

C_M_PER_S = 299_792_458.0
MAX_DOMINANT_EDGES = 3
MAX_DIFFRACTION_LOSS_DB = 30.0


@dataclass(frozen=True)
class _Pt:
    distance_m: float
    height_m: float


def _knife_edge_loss_db(v: float) -> float:
    if v <= -0.78:
        return 0.0
    return 6.9 + 20.0 * log10(sqrt((v - 0.1) ** 2 + 1.0) + v - 0.1)


def _line_height_at(a: _Pt, b: _Pt, distance_m: float) -> float:
    span = b.distance_m - a.distance_m
    if span <= 0:
        return a.height_m
    t = (distance_m - a.distance_m) / span
    return a.height_m + (b.height_m - a.height_m) * t


def _deygout(a: _Pt, b: _Pt, obstructions: list[_Pt], wavelength_m: float) -> float:
    if not obstructions:
        return 0.0

    best_v = float("-inf")
    best_idx = -1
    for i, o in enumerate(obstructions):
        d1 = o.distance_m - a.distance_m
        d2 = b.distance_m - o.distance_m
        if d1 <= 0 or d2 <= 0:
            continue
        clearance = o.height_m - _line_height_at(a, b, o.distance_m)
        v = clearance * sqrt(2.0 / wavelength_m * (1.0 / d1 + 1.0 / d2))
        if v > best_v:
            best_v, best_idx = v, i

    if best_idx == -1:
        return 0.0

    main = obstructions[best_idx]
    loss_main = _knife_edge_loss_db(best_v)
    left = [o for o in obstructions if o.distance_m < main.distance_m]
    right = [o for o in obstructions if o.distance_m > main.distance_m]
    loss_left = _deygout(a, main, left, wavelength_m)
    loss_right = _deygout(main, b, right, wavelength_m)
    return loss_main + loss_left + loss_right


def _direct_v(a: _Pt, b: _Pt, o: _Pt, wavelength_m: float) -> float:
    d1 = o.distance_m - a.distance_m
    d2 = b.distance_m - o.distance_m
    if d1 <= 0 or d2 <= 0:
        return float("-inf")
    clearance = o.height_m - _line_height_at(a, b, o.distance_m)
    return clearance * sqrt(2.0 / wavelength_m * (1.0 / d1 + 1.0 / d2))


def excess_diffraction_loss_db(
    path_length_m: float,
    tx_h: float,
    rx_h: float,
    obstructions: list[Obstruction],
    fc_hz: float,
) -> float:
    if not obstructions:
        return 0.0
    wavelength_m = C_M_PER_S / fc_hz
    a = _Pt(0.0, tx_h)
    b = _Pt(path_length_m, rx_h)
    pts = [_Pt(o.distance_along_path_m, o.height_m) for o in obstructions]

    dominant = sorted(pts, key=lambda p: -_direct_v(a, b, p, wavelength_m))[:MAX_DOMINANT_EDGES]
    dominant.sort(key=lambda p: p.distance_m)

    loss = _deygout(a, b, dominant, wavelength_m)
    return min(max(0.0, loss), MAX_DIFFRACTION_LOSS_DB)
