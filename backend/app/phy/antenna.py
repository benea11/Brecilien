"""Antenna modeling: gain, feeder/connector loss, and a vertical (elevation)
radiation pattern.

Real outdoor omni antennas are not isotropic in elevation: higher gain is
achieved by narrowing the vertical beamwidth and concentrating energy toward
the horizon, which means a link with a steep elevation angle (a leaf almost
underneath a tall relay, say) sees *less* antenna gain than one near the
horizon, even though both are nominally "omni". We model that with the same
elevation-pattern formula 3GPP TR 38.901 (table 7.3-1) uses for base-station
antenna elements:

    A_v(theta) = -min(12 * ((theta - 90) / theta_3dB)^2, SLA_v)   [dB]

where theta is measured from zenith (0 deg = straight up, 90 deg = horizon,
180 deg = straight down) and theta_3dB is the vertical half-power beamwidth.
Azimuth is assumed perfectly omnidirectional (0 dB, no azimuth dependence),
which is the whole point of this antenna class.
"""
from __future__ import annotations

from math import atan2, degrees

from pydantic import BaseModel, Field


class AntennaSpec(BaseModel):
    """A shared antenna spec applied at every radio in the project."""

    gain_dbi: float = Field(description="Peak (boresight/horizon) gain, dBi")
    elevation_beamwidth_deg: float = Field(
        description="Vertical half-power beamwidth (theta_3dB), degrees"
    )
    front_to_back_db: float = Field(
        description="Max attenuation floor of the elevation pattern (SLA_v), dB"
    )
    cable_loss_db: float = Field(description="Feeder + connector loss, one way, dB")
    polarization_loss_db: float = Field(
        default=0.0, description="Cross-polarization mismatch loss, dB"
    )


def default_omni_1900mhz() -> AntennaSpec:
    """A realistic small pole/wall-mount collinear omni for the DECT NR+
    1.9 GHz band (n1900): ~5 dBi gain traded against a ~20 deg vertical
    beamwidth (typical of a 2-3 element collinear sleeve/dipole array sold
    for DECT/GSM-1900/LTE-band-2 outdoor infrastructure use), 20 dB
    front-to-back floor, and 1 dB of feeder/connector loss.
    """
    return AntennaSpec(
        gain_dbi=5.0,
        elevation_beamwidth_deg=20.0,
        front_to_back_db=20.0,
        cable_loss_db=1.0,
        polarization_loss_db=0.0,
    )


def elevation_angle_deg(dh_m: float, horizontal_dist_m: float) -> float:
    """Angle from zenith (0=straight up, 90=horizon, 180=straight down) at
    which an observer must look to see a target `dh_m` above/below it at
    `horizontal_dist_m` away."""
    horizontal_dist_m = max(horizontal_dist_m, 1e-6)
    elevation_from_horizon = degrees(atan2(dh_m, horizontal_dist_m))
    return 90.0 - elevation_from_horizon


def vertical_pattern_gain_db(antenna: AntennaSpec, theta_deg: float) -> float:
    atten = min(
        12.0 * ((theta_deg - 90.0) / antenna.elevation_beamwidth_deg) ** 2,
        antenna.front_to_back_db,
    )
    return -atten


def link_antenna_gain_db(
    antenna: AntennaSpec,
    tx_h_m: float,
    rx_h_m: float,
    horizontal_dist_m: float,
) -> float:
    """Total antenna contribution to a single-direction link budget: TX
    element gain toward the RX's elevation angle, plus RX element gain
    toward the TX's elevation angle, minus both ends' feeder/connector loss
    and polarization mismatch."""
    theta_tx = elevation_angle_deg(rx_h_m - tx_h_m, horizontal_dist_m)
    theta_rx = elevation_angle_deg(tx_h_m - rx_h_m, horizontal_dist_m)
    tx_gain = antenna.gain_dbi + vertical_pattern_gain_db(antenna, theta_tx)
    rx_gain = antenna.gain_dbi + vertical_pattern_gain_db(antenna, theta_rx)
    return (
        tx_gain
        + rx_gain
        - 2 * antenna.cable_loss_db
        - antenna.polarization_loss_db
    )
