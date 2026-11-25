from rdflib import Literal, URIRef
from rdflib.namespace import RDF, RDFS

from mapkg.builder import feature_uri
from mapkg.ontology import GEO, MK


def test_every_feature_has_geometry_and_type(store):
    assert store.feature_count() == 40
    q = "SELECT (COUNT(*) AS ?n) WHERE { ?f a mk:Feature . FILTER NOT EXISTS { ?f geo:hasGeometry/geo:asWKT ?w } }"
    assert store.execute(q).rows[0]["n"] == 0


def test_category_kind_and_tags(store):
    r = store.execute('SELECT ?c ?cu WHERE { ?f rdfs:label "Sample Cafe VP1" ; mk:category ?c ; osmt:cuisine ?cu }')
    assert r.rows == [{"c": "amenity", "cu": "coffee_shop"}]


def test_wkt_literals_are_typed(store):
    g = store.graph
    wkts = list(g.objects(None, GEO.asWKT))
    assert wkts and all(isinstance(w, Literal) and w.datatype == GEO.wktLiteral for w in wkts)


def test_lengths_and_areas(store):
    r = store.execute('SELECT ?l WHERE { ?f rdfs:label "Marine Drive" ; mk:lengthMeters ?l }')
    assert 3000 < r.rows[0]["l"] < 5000
    r = store.execute('SELECT ?a WHERE { ?f rdfs:label "Shivaji Park" ; mk:areaSqMeters ?a }')
    assert 100_000 < r.rows[0]["a"] < 200_000


def test_osm_ids_become_osm_urls():
    assert feature_uri("node/123", 0) == URIRef("https://www.openstreetmap.org/node/123")
    assert str(feature_uri("sample/7", 0)).endswith("/feature/sample_7")
    assert str(feature_uri(None, 3)).endswith("/feature/f3")


def test_turtle_round_trip(store, tmp_path):
    from mapkg import MapStore

    p = tmp_path / "g.ttl"
    store.save(p)
    again = MapStore.from_turtle(p)
    assert len(again.graph) == len(store.graph)
    q = 'SELECT (ROUND(geof:distance("POINT(72.8347 18.9220)", "POINT(72.8355 18.9398)")) AS ?d) WHERE {}'
    assert again.execute(q).rows[0]["d"] == 1972
