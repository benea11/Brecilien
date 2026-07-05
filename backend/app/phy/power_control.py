"""Per-link adaptive transmit power control.

Rather than blasting every link at a single fixed power, the engine solves
for the minimum transmit power that closes each link at a target SINR
operating point for the selected MCS (its BLER-curve threshold plus a link
margin), capped at the configured power budget and the hard ETSI limit of
23 dBm for this band. Links that cannot close even at the cap simply run at
the cap and report whatever (poor) SINR results -- the same behavior the UI
already expects for "OFFLINE"/weak links.
"""
from __future__ import annotations

from dataclasses import dataclass

ETSI_MAX_TX_POWER_DBM = 23.0


@dataclass(frozen=True)
class PowerControlResult:
    tx_power_dbm: float
    link_closed: bool  # True if required power was <= the cap


def solve_tx_power(
    *,
    path_loss_db: float,
    antenna_gain_db: float,
    noise_floor_dbm: float,
    required_sinr_db: float,
    link_margin_db: float = 3.0,
    max_tx_power_dbm: float = ETSI_MAX_TX_POWER_DBM,
) -> PowerControlResult:
    """Solve RSSI = Ptx + antenna_gain - path_loss, SINR = RSSI - noise_floor
    for the Ptx that hits (required_sinr_db + link_margin_db), then clip to
    the power budget."""
    cap = min(max_tx_power_dbm, ETSI_MAX_TX_POWER_DBM)
    required_tx = (
        required_sinr_db
        + link_margin_db
        + noise_floor_dbm
        - antenna_gain_db
        + path_loss_db
    )
    tx_power = max(0.0, min(required_tx, cap))
    return PowerControlResult(tx_power_dbm=tx_power, link_closed=required_tx <= cap)
