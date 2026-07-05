"""Fetch MV (HTA/BT) substation locations from Enedis's public Opendatasoft
portal. Used to seed candidate node sites when a new project is created --
France-only, since this dataset has no equivalent elsewhere.

The data.gouv.fr tabular API can't serve this: the national HTA/BT datasets
listed there (Enedis, Agence ORE) are harvested remote links to external
portals, not files hosted on data.gouv.fr itself, so we query Enedis's own
Opendatasoft Explore API directly instead.
"""
from __future__ import annotations

import json
import math
import time

import httpx
from pydantic import BaseModel

ENEDIS_RECORDS_URL = "https://opendata.enedis.fr/api/explore/v2.1/catalog/datasets/poste-electrique/records"
PAGE_SIZE = 100  # server-enforced max for this endpoint
MAX_RESULTS = 500  # safety cap -- a department-wide bbox could otherwise return tens of thousands
MAX_ATTEMPTS = 3
RETRY_BACKOFF_S = 1.0
EARTH_RADIUS_M = 6_371_000.0


class MvSubstation(BaseModel):
    lat: float
    lon: float
    nom_commune: str


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def fetch_substations(min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> list[MvSubstation]:
    """The Enedis Explore API only supports a circular `within_distance`
    geo-filter (no bbox operator), so query a circle sized to cover the
    requested rectangle -- radius = distance from its center to the
    farthest corner -- then filter the results back down to the exact bbox.
    """
    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2
    radius_m = (
        max(
            _haversine_m(center_lat, center_lon, lat, lon)
            for lat in (min_lat, max_lat)
            for lon in (min_lon, max_lon)
        )
        + 50.0
    )

    headers = {"User-Agent": "dect-nrplus-planner/0.1 (local planning tool)"}
    results: list[MvSubstation] = []
    with httpx.Client(timeout=15.0, headers=headers) as client:
        offset = 0
        while offset < MAX_RESULTS:
            params = {
                "where": f"within_distance(geometry, geom'{center_lat},{center_lon}', {radius_m}m)",
                "limit": str(PAGE_SIZE),
                "offset": str(offset),
            }
            last_exc: Exception | None = None
            data = None
            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    resp = client.get(ENEDIS_RECORDS_URL, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                    break
                except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                    last_exc = exc
                    if attempt < MAX_ATTEMPTS:
                        time.sleep(RETRY_BACKOFF_S * attempt)
            if data is None:
                assert last_exc is not None
                raise last_exc

            records = data.get("results", [])
            for rec in records:
                lon, lat = json.loads(rec["geometry"])["coordinates"]
                if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
                    results.append(MvSubstation(lat=lat, lon=lon, nom_commune=rec.get("nom_commune", "")))

            total_count = data.get("total_count", 0)
            offset += PAGE_SIZE
            if len(records) < PAGE_SIZE or offset >= total_count:
                break

    return results
