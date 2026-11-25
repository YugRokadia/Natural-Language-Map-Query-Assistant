"""MapStore: load/save the knowledge graph and run *read-only* SPARQL against it."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from itertools import islice
from pathlib import Path
from typing import Any

from rdflib import Graph, Literal, URIRef
from rdflib.plugins.sparql import prepareQuery

from . import geosparql  # noqa: F401  (registers geof:* functions on import)
from .builder import build_graph, load_geojson
from .ontology import MK, PREFIXES


class QueryRejected(ValueError):
    """The query is syntactically invalid or not allowed (non read-only, federated, ...)."""


@dataclass
class QueryResult:
    query: str
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    boolean: bool | None = None  # set for ASK queries
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"columns": self.columns, "rows": self.rows, "row_count": len(self.rows)}
        if self.boolean is not None:
            d["boolean"] = self.boolean
        if self.truncated:
            d["truncated"] = True
        return d


def _plain(term: Any) -> Any:
    if term is None:
        return None
    if isinstance(term, Literal):
        py = term.toPython()
        if isinstance(py, bool | int | float):
            return py
        if isinstance(py, Decimal):
            return float(py)
        return str(term)
    return str(term)


class MapStore:
    def __init__(self, graph: Graph):
        self.graph = graph
        for prefix, ns in PREFIXES.items():
            self.graph.bind(prefix, ns, override=False)

    # ---- construction -------------------------------------------------
    @classmethod
    def from_geojson(cls, path: str | Path) -> "MapStore":
        return cls(build_graph(load_geojson(path)))

    @classmethod
    def from_turtle(cls, path: str | Path) -> "MapStore":
        g = Graph()
        g.parse(str(path), format="turtle")
        return cls(g)

    @classmethod
    def load(cls, path: str | Path) -> "MapStore":
        """Load a .ttl graph or build one from a .geojson/.json file."""
        p = Path(path)
        if p.suffix.lower() in (".ttl", ".turtle"):
            return cls.from_turtle(p)
        if p.suffix.lower() in (".geojson", ".json"):
            return cls.from_geojson(p)
        raise ValueError(f"Unsupported data file: {p} (expected .ttl, .geojson or .json)")

    def save(self, path: str | Path) -> None:
        self.graph.serialize(destination=str(path), format="turtle")

    # ---- querying -----------------------------------------------------
    @staticmethod
    def validate(query: str):
        """Parse a query and enforce: SELECT/ASK only, no SERVICE (no outbound calls)."""
        try:
            prepared = prepareQuery(query, initNs=PREFIXES)
        except Exception as exc:  # rdflib raises several parser exception types
            raise QueryRejected(f"SPARQL syntax error: {exc}") from exc
        name = prepared.algebra.name
        if name not in ("SelectQuery", "AskQuery"):
            raise QueryRejected(f"Only SELECT and ASK queries are allowed (got {name}).")
        if "ServiceGraphPattern" in repr(prepared.algebra):
            raise QueryRejected("SERVICE (federated) queries are not allowed.")
        return prepared

    def execute(self, query: str, max_rows: int = 100) -> QueryResult:
        prepared = self.validate(query)
        try:
            res = self.graph.query(prepared)
        except Exception as exc:
            raise QueryRejected(f"Query failed: {exc}") from exc

        if prepared.algebra.name == "AskQuery":
            return QueryResult(query=query, boolean=bool(res.askAnswer))

        cols = [str(v) for v in res.vars]
        rows = []
        it = iter(res)
        for r in islice(it, max_rows):
            rows.append({c: _plain(r[c]) for c in cols})
        truncated = next(it, None) is not None
        return QueryResult(query=query, columns=cols, rows=rows, truncated=truncated)

    # ---- small introspection helpers (used for prompts & the rule-based fallback) ----
    def feature_count(self) -> int:
        return len(set(self.graph.subjects(predicate=None, object=MK.Feature)))

    def kind_counts(self) -> list[tuple[str, str, int]]:
        q = """SELECT ?cat ?kind (COUNT(?f) AS ?n) WHERE {
                 ?f mk:category ?cat ; mk:kind ?kind } GROUP BY ?cat ?kind ORDER BY DESC(?n) ?kind"""
        return [(str(r.cat), str(r.kind), int(r.n)) for r in self.graph.query(q, initNs=PREFIXES)]

    def labels(self) -> list[str]:
        q = "SELECT DISTINCT ?l WHERE { ?f a mk:Feature ; rdfs:label ?l } ORDER BY ?l"
        return [str(r.l) for r in self.graph.query(q, initNs=PREFIXES)]

    def geometry_type_counts(self) -> list[tuple[str, int]]:
        q = "SELECT ?t (COUNT(?f) AS ?n) WHERE { ?f mk:geometryType ?t } GROUP BY ?t ORDER BY DESC(?n)"
        return [(str(r.t), int(r.n)) for r in self.graph.query(q, initNs=PREFIXES)]


__all__ = ["MapStore", "QueryResult", "QueryRejected", "URIRef"]
