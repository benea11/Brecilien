"""Spatially-correlated log-normal shadow fading.

A single per-link independent random draw would make the coverage heatmap
look like noise and would let two nearby grid cells (or a node and a point
1 m away) get uncorrelated shadowing, which isn't physical -- shadowing
comes from the same clutter, so nearby points should be correlated.

We synthesize one 2D Gaussian random field per LOS state (LOS/NLOS have
different empirical decorrelation distances per 3GPP TR 38.901 table
7.4.4-1) via spectral synthesis: shape white noise's spectrum to match the
2D power spectral density of an exponential covariance C(r) = exp(-r/d_corr),
which is the standard technique for generating correlated random fields
without an O(n^2) covariance-matrix Cholesky factorization. The resulting
field has zero mean and unit variance; callers scale by the project's
shadowing sigma (the UI's "SHADOWING sigma" input) and sample it at both
node positions (link budgets) and the heatmap grid, so the visualized
coverage layer and the node metrics are draws from the same physical
realization rather than independent randomness.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..geo import LocalFrame

# 3GPP TR 38.901 table 7.4.4-1 shadow-fading decorrelation distances (m).
CORRELATION_DISTANCE_M = {
    ("uma", True): 37.0,
    ("uma", False): 50.0,
    ("umi", True): 10.0,
    ("umi", False): 13.0,
    ("logd", True): 20.0,
    ("logd", False): 20.0,
}


def _spectral_synthesis_field(
    n: int, cell_m: float, corr_m: float, seed: int
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    freqs = np.fft.fftfreq(n, d=cell_m) * 2.0 * np.pi
    kx, ky = np.meshgrid(freqs, freqs, indexing="ij")
    k = np.sqrt(kx**2 + ky**2)
    # 2D spectral density of an exponential covariance exp(-r/corr_m).
    psd = 1.0 / (1.0 + (k * corr_m) ** 2) ** 1.5
    white = rng.standard_normal((n, n))
    shaped = np.fft.ifft2(np.fft.fft2(white) * np.sqrt(psd)).real
    std = shaped.std()
    if std < 1e-12:
        return shaped
    return (shaped - shaped.mean()) / std


@dataclass
class ShadowField:
    frame: LocalFrame
    origin_x: float
    origin_y: float
    cell_m: float
    n: int
    field_los: np.ndarray
    field_nlos: np.ndarray

    def _bilinear(self, field: np.ndarray, x: float, y: float) -> float:
        gx = (x - self.origin_x) / self.cell_m
        gy = (y - self.origin_y) / self.cell_m
        gx = min(max(gx, 0.0), self.n - 1.001)
        gy = min(max(gy, 0.0), self.n - 1.001)
        ix, iy = int(gx), int(gy)
        fx, fy = gx - ix, gy - iy
        v00, v10 = field[ix, iy], field[ix + 1, iy]
        v01, v11 = field[ix, iy + 1], field[ix + 1, iy + 1]
        return (
            v00 * (1 - fx) * (1 - fy)
            + v10 * fx * (1 - fy)
            + v01 * (1 - fx) * fy
            + v11 * fx * fy
        )

    def sample(self, lat: float, lon: float, los: bool) -> float:
        """Returns a zero-mean, unit-variance correlated sample; scale by
        the desired shadowing sigma (dB) before adding to a link budget."""
        x, y = self.frame.to_xy(lat, lon)
        field = self.field_los if los else self.field_nlos
        return self._bilinear(field, x, y)


def build_shadow_field(
    frame: LocalFrame,
    extent_m: float,
    model: str,
    seed: int,
    cell_m: float = 15.0,
) -> ShadowField:
    n = max(32, int(2 * extent_m / cell_m))
    # round up to a size FFT handles efficiently
    n = 1 << (n - 1).bit_length()
    origin = -(n * cell_m) / 2.0
    corr_los = CORRELATION_DISTANCE_M.get((model, True), 30.0)
    corr_nlos = CORRELATION_DISTANCE_M.get((model, False), 40.0)
    field_los = _spectral_synthesis_field(n, cell_m, corr_los, seed)
    field_nlos = _spectral_synthesis_field(n, cell_m, corr_nlos, seed + 1)
    return ShadowField(
        frame=frame,
        origin_x=origin,
        origin_y=origin,
        cell_m=cell_m,
        n=n,
        field_los=field_los,
        field_nlos=field_nlos,
    )
