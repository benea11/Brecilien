"""Band/channel -> carrier frequency mapping for the UI's BAND and CHANNEL
dropdowns (DECT NR+ n1900 EU band and the US 902 MHz band).

Band 1 (EU, n1900) spans 1881.792-1897.344 MHz with the classic DECT
1.728 MHz channel raster (ETSI TS 103 636-2 / historically carriers 0-9),
giving 10 channels numbered 1657-1666."""
from __future__ import annotations

B1_CHANNEL_FREQ_HZ = {
    "1657": 1881.8e6,
    "1658": 1883.5e6,
    "1659": 1885.2e6,
    "1660": 1887.0e6,
    "1661": 1888.7e6,
    "1662": 1890.4e6,
    "1663": 1892.2e6,
    "1664": 1893.9e6,
    "1665": 1895.6e6,
    "1666": 1897.3e6,
}
B2_DEFAULT_FREQ_HZ = 902.0e6


def carrier_frequency_hz(band: str, channel: str) -> float:
    if band == "b2":
        return B2_DEFAULT_FREQ_HZ
    return B1_CHANNEL_FREQ_HZ.get(channel, 1881.8e6)
