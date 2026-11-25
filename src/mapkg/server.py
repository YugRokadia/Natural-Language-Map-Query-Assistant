"""MCP server exposing the map knowledge graph to any MCP client (Claude Desktop, Claude Code, ...).

Tools
-----
describe_dataset()          vocabulary, spatial functions, and what's in the data
ask_map(question)           natural language -> SPARQL -> results (LLM, rules as fallback)
run_sparql(query)           run your own read-only SELECT/ASK query
find_nearby(lat, lon, ...)  features within a radius of a coordinate
"""

from __future__ import annotations

import os
from pathlib import Path

from .assistant import MapAssistant
from .llm import TranslationError
from .schema import schema_summary
from .store import MapStore, QueryRejected

try:  # MCP Python SDK v2
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # MCP Python SDK v1
    from mcp.server.fastmcp import FastMCP as _Server

MAX_ROWS = 500
INSTRUCTIONS = (
    "Answer geographic questions over an OpenStreetMap knowledge graph. Prefer ask_map for plain-English "
    "questions; call describe_dataset first if you want to write SPARQL yourself with run_sparql. "
    "Distances are in metres."
)


def default_data_path() -> Path:
    env = os.environ.get("MAPKG_DATA")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "data" / "sample_mumbai.geojson"


def create_server(store: MapStore, assistant: MapAssistant | None = None):
    assistant = assistant or MapAssistant(store)
    mcp = _Server("mapkg", instructions=INSTRUCTIONS)

    @mcp.tool()
    def describe_dataset() -> str:
        """Describe the graph vocabulary, spatial functions and available place types/names."""
        return schema_summary(store)

    @mcp.tool()
    def ask_map(question: str) -> dict:
        """Answer a natural-language map question. Returns the generated SPARQL and the result rows."""
        try:
            return assistant.ask(question).to_dict()
        except (TranslationError, QueryRejected) as exc:
            return {"error": str(exc), "hint": "Rephrase, or call describe_dataset and use run_sparql."}

    @mcp.tool()
    def run_sparql(query: str, max_rows: int = 100) -> dict:
        """Run a read-only SPARQL SELECT/ASK query (prefixes rdf, rdfs, xsd, geo, geof, mk, osmt, osm are predeclared)."""
        try:
            return store.execute(query, max_rows=max(1, min(max_rows, MAX_ROWS))).to_dict()
        except QueryRejected as exc:
            return {"error": str(exc)}

    @mcp.tool()
    def find_nearby(lat: float, lon: float, radius_m: float = 1000, kind: str | None = None, limit: int = 25) -> dict:
        """List features within radius_m metres of a WGS84 point, optionally filtered by mk:kind (e.g. 'cafe')."""
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return {"error": "lat must be in [-90, 90] and lon in [-180, 180]."}
        kind_clause = ""
        if kind:
            kind_clause = '?f mk:kind "' + kind.replace("\\", "\\\\").replace('"', '\\"') + '" .'
        q = f"""SELECT ?name ?kind (ROUND(geof:distance(?wkt, "POINT({lon} {lat})")) AS ?distance_m) WHERE {{
  ?f a mk:Feature ; geo:hasGeometry/geo:asWKT ?wkt . {kind_clause}
  OPTIONAL {{ ?f rdfs:label ?name }} OPTIONAL {{ ?f mk:kind ?kind }}
  FILTER(geof:distance(?wkt, "POINT({lon} {lat})") <= {float(radius_m)})
}} ORDER BY ?distance_m LIMIT {max(1, min(int(limit), MAX_ROWS))}"""
        try:
            return {"sparql": q, **store.execute(q, max_rows=MAX_ROWS).to_dict()}
        except QueryRejected as exc:
            return {"error": str(exc)}

    @mcp.resource("mapkg://schema")
    def schema_resource() -> str:
        """The dataset vocabulary and contents."""
        return schema_summary(store)

    return mcp


def main(path: str | Path | None = None) -> None:
    store = MapStore.load(path or default_data_path())
    create_server(store).run()  # stdio transport


if __name__ == "__main__":
    main()
