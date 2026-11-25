"""Namespaces and vocabulary used by the knowledge graph.

Model (a small subset of GeoSPARQL 1.0 plus a thin OSM layer):

    osm:node/123  a  geo:Feature, mk:Feature ;
                  rdfs:label       "Juhu Beach" ;
                  mk:category      "leisure" ;        # primary OSM tag key
                  mk:kind          "beach_resort" ;   # primary OSM tag value
                  mk:geometryType  "Point" ;
                  osmt:<key>       "<value>" ;        # every other OSM tag
                  geo:hasGeometry  [ a geo:Geometry ;
                                     geo:asWKT "POINT(72.82 19.09)"^^geo:wktLiteral ] .
"""

from rdflib import Namespace
from rdflib.namespace import RDF, RDFS, XSD

GEO = Namespace("http://www.opengis.net/ont/geosparql#")
GEOF = Namespace("http://www.opengis.net/def/function/geosparql/")
MK = Namespace("https://example.org/mapkg#")
OSMT = Namespace("https://example.org/mapkg/tag/")
OSM = Namespace("https://www.openstreetmap.org/")
FEATURE = Namespace("https://example.org/mapkg/feature/")

# Prefixes that are always available to queries (callers don't need to declare them).
PREFIXES = {
    "rdf": RDF,
    "rdfs": RDFS,
    "xsd": XSD,
    "geo": GEO,
    "geof": GEOF,
    "mk": MK,
    "osmt": OSMT,
    "osm": OSM,
}

# First matching key wins when picking a feature's primary category.
CATEGORY_KEYS = [
    "amenity", "shop", "tourism", "leisure", "railway", "public_transport",
    "aeroway", "highway", "historic", "natural", "waterway", "landuse",
    "building", "place", "man_made",
]

# Tags that become dedicated properties rather than osmt:* literals.
RESERVED_TAGS = {"name"}
