"""Fetch real building footprints (with height, where tagged) from
OpenStreetMap via the Overpass API, for LOS/NLOS geometry checks, rooftop
diffraction, and O2I containment tests. Responses are cached to disk keyed
by a rounded bounding box, since the same project area is queried on every
node edit and every simulate call.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import httpx

from .models import Building

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "osm"
DEFAULT_BUILDING_HEIGHT_M = 9.0  # ~3 storeys, used when OSM has no height/levels tag
METERS_PER_LEVEL = 3.0
BBOX_ROUND_DECIMALS = 4  # ~11 m grid, keeps cache keys stable across small pans
MAX_ATTEMPTS = 3
RETRY_BACKOFF_S = 1.5


def _cache_key(min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> str:
    rounded = [
        round(v, BBOX_ROUND_DECIMALS) for v in (min_lat, min_lon, max_lat, max_lon)
    ]
    digest = hashlib.sha1(json.dumps(rounded).encode()).hexdigest()[:16]
    return digest


def _parse_height(tags: dict) -> float:
    if "height" in tags:
        try:
            return float(str(tags["height"]).split()[0])
        except ValueError:
            pass
    if "building:levels" in tags:
        try:
            return float(tags["building:levels"]) * METERS_PER_LEVEL
        except ValueError:
            pass
    return DEFAULT_BUILDING_HEIGHT_M


def _overpass_query(min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> str:
    bbox = f"{min_lat},{min_lon},{max_lat},{max_lon}"
    return f"""
    [out:json][timeout:25];
    (
      way["building"]({bbox});
      relation["building"]({bbox});
    );
    out body;
    >;
    out skel qt;
    """


def _closed_ring(coords: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(coords) < 3:
        return []
    if coords[0] != coords[-1]:
        coords = coords + [coords[0]]
    return coords


def _assemble_outer_rings(
    way_node_id_lists: list[list[int]], node_coords: dict[int, tuple[float, float]]
) -> list[list[tuple[float, float]]]:
    """Chain a multipolygon relation's "outer" member ways into one or more
    closed rings by matching shared endpoint node ids. A single building
    outline is frequently split across several ways in OSM (that's the
    usual reason it's modeled as a relation instead of one way), so they
    can't just be used as independent footprints the way a plain
    `way["building"]` can."""
    remaining = [ids for ids in way_node_id_lists if len(ids) >= 2]
    rings: list[list[int]] = []
    while remaining:
        ring = list(remaining.pop(0))
        merged = True
        while merged and ring[0] != ring[-1] and remaining:
            merged = False
            for i, ids in enumerate(remaining):
                if ids[0] == ring[-1]:
                    ring.extend(ids[1:])
                elif ids[-1] == ring[-1]:
                    ring.extend(reversed(ids[:-1]))
                elif ids[-1] == ring[0]:
                    ring[0:0] = ids[:-1]
                elif ids[0] == ring[0]:
                    ring[0:0] = reversed(ids[1:])
                else:
                    continue
                remaining.pop(i)
                merged = True
                break
        rings.append(ring)

    result: list[list[tuple[float, float]]] = []
    for ring in rings:
        coords = [node_coords[n] for n in ring if n in node_coords]
        closed = _closed_ring(coords)
        if closed:
            result.append(closed)
    return result


def _elements_to_buildings(elements: list[dict]) -> list[Building]:
    node_coords = {el["id"]: (el["lon"], el["lat"]) for el in elements if el["type"] == "node"}
    ways_by_id = {el["id"]: el for el in elements if el["type"] == "way" and "nodes" in el}
    buildings: list[Building] = []

    for el in elements:
        # Only ways directly tagged `building` are footprints on their own --
        # a relation's untagged member ways (outer/inner ring segments) must
        # not also be counted as separate buildings.
        if el["type"] != "way" or "building" not in el.get("tags", {}):
            continue
        coords = _closed_ring([node_coords[n] for n in el["nodes"] if n in node_coords])
        if not coords:
            continue
        buildings.append(
            Building(
                id=f"way/{el['id']}",
                height_m=_parse_height(el.get("tags", {})),
                footprint=[list(c) for c in coords],
            )
        )

    for el in elements:
        if el["type"] != "relation" or "building" not in el.get("tags", {}):
            continue
        outer_way_ids = [
            m["ref"] for m in el.get("members", []) if m.get("type") == "way" and m.get("role") == "outer"
        ]
        way_node_id_lists = [ways_by_id[wid]["nodes"] for wid in outer_way_ids if wid in ways_by_id]
        height_m = _parse_height(el.get("tags", {}))
        rings = _assemble_outer_rings(way_node_id_lists, node_coords)
        for i, ring in enumerate(rings):
            building_id = f"relation/{el['id']}" if len(rings) == 1 else f"relation/{el['id']}/{i}"
            buildings.append(Building(id=building_id, height_m=height_m, footprint=[list(c) for c in ring]))

    return buildings


def fetch_buildings(
    min_lat: float, min_lon: float, max_lat: float, max_lon: float
) -> list[Building]:
    """Synchronous by design: the whole simulation engine (this function's
    only I/O) runs inside a worker thread (see main.py's use of
    asyncio.to_thread) so the FastAPI event loop stays free to stream SSE
    progress events while the Monte Carlo trials run."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = _cache_key(min_lat, min_lon, max_lat, max_lon)
    cache_file = CACHE_DIR / f"{key}.json"
    if cache_file.exists():
        raw = json.loads(cache_file.read_text())
    else:
        query = _overpass_query(min_lat, min_lon, max_lat, max_lon)
        headers = {
            "User-Agent": "dect-nrplus-planner/0.1 (local planning tool)",
            "Accept": "application/json, */*;q=0.8",
        }
        # The public Overpass instance occasionally has transient DNS/connect
        # hiccups or 429/504s under load -- retry a couple of times before
        # surfacing an error to the simulation run.
        last_exc: Exception | None = None
        raw = None
        with httpx.Client(timeout=30.0, headers=headers) as client:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    resp = client.post(OVERPASS_URL, data={"data": query})
                    resp.raise_for_status()
                    raw = resp.json()
                    break
                except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                    last_exc = exc
                    if attempt < MAX_ATTEMPTS:
                        time.sleep(RETRY_BACKOFF_S * attempt)
        if raw is None:
            assert last_exc is not None
            raise last_exc
        cache_file.write_text(json.dumps(raw))
    return _elements_to_buildings(raw.get("elements", []))
