"""Describe the graph (vocabulary, spatial functions, contents) in a form an LLM can use."""

from __future__ import annotations

from .store import MapStore

VOCAB = """\
PREFIXES (already declared - never write PREFIX lines):
  rdf, rdfs, xsd, geo (GeoSPARQL), geof (GeoSPARQL functions), mk (<https://example.org/mapkg#>),
  osmt (<https://example.org/mapkg/tag/>), osm (<https://www.openstreetmap.org/>)

DATA MODEL - every map object is an mk:Feature:
  ?f rdfs:label ?name .                     # name (not every feature has one)
  ?f mk:category ?cat .                     # primary OSM key, e.g. "amenity", "railway", "leisure", "highway"
  ?f mk:kind ?kind .                        # primary OSM value, e.g. "cafe", "hospital", "station", "park"
  ?f mk:geometryType ?t .                   # "Point" | "LineString" | "Polygon" (| Multi*)
  ?f mk:lengthMeters ?len .                 # LineStrings only
  ?f mk:areaSqMeters ?area .                # Polygons only
  ?f osmt:<key> "<value>" .                 # every other OSM tag, e.g. osmt:cuisine "indian", osmt:lanes "3"
  ?f geo:hasGeometry/geo:asWKT ?wkt .       # geometry as WKT (lon lat order, WGS84)

SPATIAL FUNCTIONS (use inside FILTER / BIND / SELECT):
  geof:distance(?wktA, ?wktB)   -> distance in METRES (xsd:double)
  geof:sfWithin(?wktA, ?wktB)   -> true if A lies inside B
  geof:sfContains(?wktA, ?wktB) -> true if A contains B
  geof:sfIntersects(?wktA, ?wktB)

RULES:
  * Output exactly one SPARQL SELECT or ASK query inside a ```sparql fenced block. No other text.
  * Match place names via rdfs:label with exact, case-sensitive strings copied from the NAMED FEATURES list
    when possible; otherwise FILTER(CONTAINS(LCASE(STR(?label)), "text")).
  * Bind the anchor's WKT separately from the candidates' WKT (?wkt0 vs ?wkt) and exclude the anchor itself (FILTER(?f != ?anchor)).
  * "near"/"nearby" with no number means within 1000 metres. Convert km to metres.
  * For "nearest" use ORDER BY on the distance and LIMIT 1 (or the requested count).
  * Use mk:kind for things like cafes/hospitals/parks; use mk:category "highway" for roads.
  * Return human-friendly columns (?name, ?kind, distance as ROUND(...) AS ?distance_m). Add LIMIT 50 to listings.
"""

EXAMPLES = """\
EXAMPLES
Q: Which hospitals are within 3 km of Bandra?
```sparql
SELECT ?name (ROUND(geof:distance(?wkt, ?wkt0)) AS ?distance_m) WHERE {
  ?anchor rdfs:label "Bandra" ; geo:hasGeometry/geo:asWKT ?wkt0 .
  ?f mk:kind "hospital" ; rdfs:label ?name ; geo:hasGeometry/geo:asWKT ?wkt .
  FILTER(?f != ?anchor && geof:distance(?wkt, ?wkt0) <= 3000)
} ORDER BY ?distance_m LIMIT 50
```
Q: What is the largest park?
```sparql
SELECT ?name ?area_sqm WHERE { ?f mk:kind "park" ; rdfs:label ?name ; mk:areaSqMeters ?area_sqm }
ORDER BY DESC(?area_sqm) LIMIT 1
```
Q: How many cafes serve coffee_shop cuisine?
```sparql
SELECT (COUNT(?f) AS ?count) WHERE { ?f mk:kind "cafe" ; osmt:cuisine "coffee_shop" }
```
"""


def schema_summary(store: MapStore, max_kinds: int = 40, max_labels: int = 80) -> str:
    kinds = store.kind_counts()[:max_kinds]
    labels = store.labels()[:max_labels]
    geom = ", ".join(f"{t}: {n}" for t, n in store.geometry_type_counts())
    kinds_txt = "\n".join(f'  mk:category "{c}" / mk:kind "{k}": {n}' for c, k, n in kinds)
    return (
        f"{VOCAB}\nDATASET: {store.feature_count()} features ({geom})\n\n"
        f"FEATURE KINDS (count):\n{kinds_txt}\n\n"
        f"NAMED FEATURES (up to {max_labels}):\n  " + "; ".join(labels) + f"\n\n{EXAMPLES}"
    )
