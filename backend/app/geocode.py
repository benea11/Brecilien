"""Location search for the "new project" flow, via OSM's Nominatim --
same data ecosystem as the building footprints in osm.py, so one attribution
story and one courtesy User-Agent policy covers both.
"""
from __future__ import annotations

import time

import httpx
from pydantic import BaseModel

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
MAX_ATTEMPTS = 3
RETRY_BACKOFF_S = 1.0


class GeocodeResult(BaseModel):
    display_name: str
    lat: float
    lon: float
    country_code: str = ""


def search(query: str, limit: int = 5) -> list[GeocodeResult]:
    headers = {"User-Agent": "dect-nrplus-planner/0.1 (local planning tool)"}
    # addressdetails=1 buys us address.country_code, which the frontend uses
    # to gate the "add MV substations" option to French results only (that
    # dataset is Enedis/France-only) -- works the same whether the match is
    # a commune, a department, or a department name.
    params = {"q": query, "format": "jsonv2", "limit": str(limit), "addressdetails": "1"}
    last_exc: Exception | None = None
    with httpx.Client(timeout=15.0, headers=headers) as client:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                resp = client.get(NOMINATIM_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
                return [
                    GeocodeResult(
                        display_name=d["display_name"],
                        lat=float(d["lat"]),
                        lon=float(d["lon"]),
                        country_code=d.get("address", {}).get("country_code", ""),
                    )
                    for d in data
                ]
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_exc = exc
                if attempt < MAX_ATTEMPTS:
                    time.sleep(RETRY_BACKOFF_S * attempt)
    assert last_exc is not None
    raise last_exc
