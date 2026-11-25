"""GeoSPARQL-style filter functions for rdflib, implemented with Shapely + pyproj.

rdflib has no built-in GeoSPARQL support, so we register the handful of functions
that natural-language map questions need:

    geof:distance(?wkt1, ?wkt2)      -> distance in METRES (geodesic-accurate, local projection)
    geof:sfIntersects(?a, ?b)        -> boolean
    geof:sfWithin(?a, ?b)            -> boolean  (a is within b)
    geof:sfContains(?a, ?b)          -> boolean  (a contains b)

Coordinates are WGS84 lon/lat, as in OSM and GeoJSON.
"""

from __future__ import annotations

import re
from functools import lru_cache

import numpy as np
import shapely
from pyproj import CRS, Transformer
from rdflib import Literal
from rdflib.namespace import XSD
from rdflib.plugins.sparql.operators import register_custom_function
from shapely import wkt as shapely_wkt

from .ontology import GEOF

_CRS_PREFIX = re.compile(r"^\s*<[^>]+>\s*")


@lru_cache(maxsize=65536)
def parse_wkt(text: str) -> shapely.Geometry:
    return shapely_wkt.loads(_CRS_PREFIX.sub("", text))


@lru_cache(maxsize=256)
def _local_transformer(lat: float, lon: float) -> Transformer:
    crs = CRS.from_proj4(f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m +no_defs")
    return Transformer.from_crs("EPSG:4326", crs, always_xy=True)


def distance_m(a: shapely.Geometry, b: shapely.Geometry) -> float:
    """Shortest distance between two lon/lat geometries, in metres."""
    c = a.centroid
    t = _local_transformer(round(c.y, 2), round(c.x, 2))
    def project(g: shapely.Geometry) -> shapely.Geometry:
        return shapely.transform(g, lambda xy: np.column_stack(t.transform(xy[:, 0], xy[:, 1])))

    return float(project(a).distance(project(b)))


def _geoms(*args) -> tuple[shapely.Geometry, shapely.Geometry]:
    return parse_wkt(str(args[0])), parse_wkt(str(args[1]))


def _distance(*args):
    a, b = _geoms(*args)  # an optional 3rd (units) argument is accepted and ignored: always metres
    return Literal(round(distance_m(a, b), 2), datatype=XSD.double)


def _intersects(*args):
    a, b = _geoms(*args)
    return Literal(bool(a.intersects(b)))


def _within(*args):
    a, b = _geoms(*args)
    return Literal(bool(a.within(b)))


def _contains(*args):
    a, b = _geoms(*args)
    return Literal(bool(a.contains(b)))


FUNCTIONS = {
    GEOF.distance: _distance,
    GEOF.sfIntersects: _intersects,
    GEOF.sfWithin: _within,
    GEOF.sfContains: _contains,
}


def register() -> None:
    for uri, fn in FUNCTIONS.items():
        register_custom_function(uri, fn, override=True)


register()
