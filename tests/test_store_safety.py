import pytest

from mapkg.store import QueryRejected


@pytest.mark.parametrize("q", [
    "INSERT DATA { <urn:a> <urn:b> <urn:c> }",
    "DELETE WHERE { ?s ?p ?o }",
    "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
    "DESCRIBE <urn:a>",
    "SELECT * WHERE { SERVICE <https://dbpedia.org/sparql> { ?s ?p ?o } }",
    "SELEC nonsense",
])
def test_rejects_unsafe_or_invalid(store, q):
    with pytest.raises(QueryRejected):
        store.execute(q)


def test_graph_not_modified_by_rejected_update(store):
    before = len(store.graph)
    with pytest.raises(QueryRejected):
        store.execute("INSERT DATA { <urn:a> <urn:b> <urn:c> }")
    assert len(store.graph) == before


def test_row_cap_and_truncation(store):
    r = store.execute("SELECT ?f WHERE { ?f a mk:Feature }", max_rows=5)
    assert len(r.rows) == 5 and r.truncated
    r = store.execute("SELECT ?f WHERE { ?f a mk:Feature }", max_rows=1000)
    assert len(r.rows) == 40 and not r.truncated


def test_ask_query(store):
    assert store.execute('ASK { ?f mk:kind "hospital" }').boolean is True
    assert store.execute('ASK { ?f mk:kind "spaceport" }').boolean is False
