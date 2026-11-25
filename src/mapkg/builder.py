"""Turn OpenStreetMap-style GeoJSON into an RDF knowledge graph (GeoPandas + Shapely + rdflib)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from .ontology import (
    CATEGORY_KEYS, FEATURE, GEO, MK, OSM, OSMT, PREFIXES, RESERVED_TAGS,
)

_OSM_ID = re.compile(r"^(node|way|relation)/(-?\d+)$")


def load_geojson(path: str | Path) -> gpd.GeoDataFrame:
    """Read a GeoJSON FeatureCollection, keeping each feature's top-level ``id``."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    feats = data["features"] if data.get("type") == "FeatureCollection" else [data]
    for f in feats:
        props = f.setdefault("properties", {}) or {}
        props["_id"] = f.get("id") or props.get("@id") or props.get("id")
        f["properties"] = props
    return gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326")


def feature_uri(raw_id: object, fallback_index: int) -> URIRef:
    """Real OSM ids (node/123) map to openstreetmap.org URLs; anything else gets a local IRI."""
    if raw_id is not None and not pd.isna(raw_id):
        s = str(raw_id)
        if _OSM_ID.match(s):
            return OSM[s]
        return FEATURE[re.sub(r"[^A-Za-z0-9_.~-]", "_", s)]
    return FEATURE[f"f{fallback_index}"]


def primary_category(row: pd.Series) -> tuple[str, str] | None:
    for key in CATEGORY_KEYS:
        val = row.get(key)
        if val is not None and not pd.isna(val) and str(val) not in ("", "no"):
            return key, str(val)
    return None


def _metric_measures(gdf: gpd.GeoDataFrame) -> tuple[pd.Series, pd.Series]:
    """Length (m) for lines and area (m²) for polygons, via a local UTM projection."""
    if gdf.empty:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    proj = gdf.to_crs(gdf.estimate_utm_crs())
    return proj.geometry.length, proj.geometry.area


def build_graph(gdf: gpd.GeoDataFrame) -> Graph:
    """Build the RDF graph. Every row of ``gdf`` becomes one ``mk:Feature``."""
    g = Graph()
    for prefix, ns in PREFIXES.items():
        g.bind(prefix, ns)

    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].reset_index(drop=True)
    length_m, area_m2 = _metric_measures(gdf)
    skip = {"geometry", "_id", *CATEGORY_KEYS, *RESERVED_TAGS}

    for i, row in gdf.iterrows():
        uri = feature_uri(row.get("_id"), i)
        geom = row.geometry
        g.add((uri, RDF.type, GEO.Feature))
        g.add((uri, RDF.type, MK.Feature))

        name = row.get("name")
        if name is not None and not pd.isna(name) and str(name).strip():
            g.add((uri, RDFS.label, Literal(str(name))))

        cat = primary_category(row)
        if cat:
            g.add((uri, MK.category, Literal(cat[0])))
            g.add((uri, MK.kind, Literal(cat[1])))

        g.add((uri, MK.geometryType, Literal(geom.geom_type)))
        if geom.geom_type in ("LineString", "MultiLineString"):
            g.add((uri, MK.lengthMeters, Literal(round(float(length_m[i]), 1), datatype=XSD.double)))
        elif geom.geom_type in ("Polygon", "MultiPolygon"):
            g.add((uri, MK.areaSqMeters, Literal(round(float(area_m2[i]), 1), datatype=XSD.double)))

        # Remaining tags become osmt:<key> literals. Category tags are kept too, so
        # `osmt:amenity "cafe"` and `mk:kind "cafe"` are both valid ways to ask.
        for key, val in row.items():
            if key in skip or val is None or (not isinstance(val, (list, dict)) and pd.isna(val)):
                continue
            g.add((uri, OSMT[re.sub(r"\s+", "_", str(key))], Literal(str(val))))
        for key in CATEGORY_KEYS:
            val = row.get(key)
            if val is not None and not pd.isna(val):
                g.add((uri, OSMT[key], Literal(str(val))))

        geom_node = URIRef(f"{uri}/geom")
        g.add((uri, GEO.hasGeometry, geom_node))
        g.add((geom_node, RDF.type, GEO.Geometry))
        wkt = shapely.to_wkt(geom, rounding_precision=6)
        g.add((geom_node, GEO.asWKT, Literal(wkt, datatype=GEO.wktLiteral)))

    return g
