import json

from mapkg import MapStore
from mapkg.overpass import build_query, to_geojson

PAYLOAD = {"elements": [
    {"type": "node", "id": 1, "lat": 19.1, "lon": 72.83, "tags": {"amenity": "cafe", "name": "Real Cafe"}},
    {"type": "node", "id": 2, "lat": 19.1, "lon": 72.83},  # untagged: skipped
    {"type": "way", "id": 10, "tags": {"leisure": "park", "name": "Tiny Park"}, "geometry": [
        {"lat": 19.0, "lon": 72.8}, {"lat": 19.0, "lon": 72.81}, {"lat": 19.01, "lon": 72.81}, {"lat": 19.0, "lon": 72.8}]},
    {"type": "way", "id": 11, "tags": {"highway": "primary", "name": "Ring Rd"}, "geometry": [
        {"lat": 19.0, "lon": 72.8}, {"lat": 19.0, "lon": 72.81}, {"lat": 19.01, "lon": 72.81}, {"lat": 19.0, "lon": 72.8}]},
    {"type": "relation", "id": 20, "tags": {"name": "skipped"}},
]}


def test_conversion_shapes():
    fc = to_geojson(PAYLOAD)
    by_id = {f["id"]: f for f in fc["features"]}
    assert set(by_id) == {"node/1", "way/10", "way/11"}
    assert by_id["node/1"]["geometry"]["type"] == "Point"
    assert by_id["way/10"]["geometry"]["type"] == "Polygon"
    assert by_id["way/11"]["geometry"]["type"] == "LineString"  # closed highway is still a line


def test_converted_data_loads_into_graph(tmp_path):
    p = tmp_path / "x.geojson"
    p.write_text(json.dumps(to_geojson(PAYLOAD)))
    s = MapStore.from_geojson(p)
    assert s.execute("ASK { <https://www.openstreetmap.org/node/1> mk:kind 'cafe' }").boolean
    assert s.execute('ASK { ?f rdfs:label "Tiny Park" ; mk:areaSqMeters ?a }').boolean


def test_query_contains_bbox_and_out_clause():
    q = build_query(19.0, 72.8, 19.1, 72.9)
    assert "(19.0,72.8,19.1,72.9)" in q and q.strip().endswith("out tags geom;")
