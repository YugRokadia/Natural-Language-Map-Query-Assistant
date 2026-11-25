"""Fetch real OpenStreetMap data from the Overpass API and convert it to GeoJSON.

Only nodes and ways are converted (relations/multipolygons are skipped to keep the
converter dependency-free). Run on a machine with internet access:

    mapkg fetch --bbox 19.05 72.80 19.15 72.90 --out data/mumbai_west.geojson
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# (tag key, regex of accepted values or None for "any value"), applied to nodes and ways.
SELECTORS: list[tuple[str, str | None]] = [
    ("amenity", "hospital|clinic|pharmacy|cafe|restaurant|school|university|college|bank|atm|place_of_worship|fuel|police|library|cinema"),
    ("railway", "station|halt|subway_entrance"),
    ("tourism", "attraction|museum|viewpoint|hotel|gallery|zoo"),
    ("leisure", "park|garden|nature_reserve|stadium|playground"),
    ("aeroway", "aerodrome|terminal"),
    ("natural", "beach|water"),
]
ROAD_CLASSES = "motorway|trunk|primary|secondary|tertiary"
_NOT_AREAS = {"highway", "barrier", "railway", "waterway"}


def build_query(south: float, west: float, north: float, east: float, timeout: int = 90) -> str:
    bbox = f"({south},{west},{north},{east})"
    parts = []
    for key, vals in SELECTORS:
        flt = f'["{key}"~"^({vals})$"]' if vals else f'["{key}"]'
        parts += [f"  node{flt}{bbox};", f"  way{flt}{bbox};"]
    parts.append(f'  way["highway"~"^({ROAD_CLASSES})$"]{bbox};')
    return f"[out:json][timeout:{timeout}];\n(\n" + "\n".join(parts) + "\n);\nout tags geom;"


def fetch(query: str, url: str = OVERPASS_URL, timeout: int = 120) -> dict:
    req = urllib.request.Request(
        url, data=urllib.parse.urlencode({"data": query}).encode(),
        headers={"User-Agent": "mapkg/0.1 (educational project)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def to_geojson(overpass: dict) -> dict:
    """Convert an Overpass ``out tags geom`` JSON payload into a GeoJSON FeatureCollection."""
    feats = []
    for el in overpass.get("elements", []):
        tags = el.get("tags")
        if not tags:
            continue
        kind = el.get("type")
        if kind == "node" and "lat" in el:
            geom = {"type": "Point", "coordinates": [el["lon"], el["lat"]]}
        elif kind == "way" and len(el.get("geometry") or []) >= 2:
            coords = [[p["lon"], p["lat"]] for p in el["geometry"]]
            closed = len(coords) >= 4 and coords[0] == coords[-1]
            is_area = closed and not (_NOT_AREAS & tags.keys()) and tags.get("area") != "no"
            geom = {"type": "Polygon", "coordinates": [coords]} if is_area else \
                   {"type": "LineString", "coordinates": coords}
        else:
            continue  # relations and incomplete ways are skipped
        feats.append({"type": "Feature", "id": f"{kind}/{el['id']}", "properties": dict(tags), "geometry": geom})
    return {"type": "FeatureCollection", "features": feats}
