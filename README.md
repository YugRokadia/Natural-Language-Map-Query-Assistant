# mapkg: Natural-Language Map Query Assistant

Ask map questions in plain English. **OpenStreetMap data is modelled as an RDF knowledge graph**
(GeoPandas + Shapely + rdflib), **an LLM translates your question into SPARQL**, and the whole thing is
**exposed as an MCP server** so Claude Desktop / Claude Code (or any MCP client) can use it as a tool.

```
 "Which cafes are within 1 km of NMIMS?"
          │
          ▼
 ┌─────────────────┐   schema + examples    ┌────────────────────┐
 │ LLM (Anthropic) │ ◄───────────────────── │ schema.py          │
 │ NL → SPARQL     │                        │ (built from graph) │
 └───────┬─────────┘                        └────────────────────┘
         │ SPARQL                 invalid? error is fed back, retry ×2
         ▼
 ┌─────────────────┐  read-only guard (SELECT/ASK only, no SERVICE)
 │ MapStore.execute│───────────────────────────────┐
 └───────┬─────────┘                               ▼
         │                              ┌──────────────────────┐
         ▼                              │ rdflib graph          │
   rows + the SPARQL used               │  mk:Feature, geo:asWKT│
         ▲                              │  geof:distance (Shapely│
         │                              │  + pyproj, in metres) │
   MCP tools: ask_map · run_sparql ·    └──────────▲───────────┘
   find_nearby · describe_dataset                  │ builder.py
                                       GeoJSON (OSM/Overpass) via GeoPandas
```

If no `ANTHROPIC_API_KEY` is set (or the API call fails), a deterministic **rule-based translator**
answers the common question shapes, so the project runs and is testable offline.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                      # 46 tests

mapkg ask "Which cafes are within 1 km of NMIMS?"
mapkg ask "nearest pharmacy to NMIMS Mumbai Campus"
mapkg ask "distance between Dadar and Bandra"
mapkg ask "largest park"
mapkg sparql 'SELECT ?n WHERE { ?f mk:kind "hospital"; rdfs:label ?n }'
mapkg schema                # the vocabulary/prompt the LLM sees
```

Use the LLM translator (free-form questions):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export MAPKG_MODEL=claude-sonnet-5-5     # optional; any Claude model id
mapkg ask "Are there any 24-hour pharmacies between the airport and Vile Parle station?"
```

`MAPKG_ENGINE=auto|llm|rules` controls the engine (`auto` = LLM if a key is set, rules as fallback).

## Use it from Claude (MCP)

**Claude Desktop** (`claude_desktop_config.json`) – use absolute paths:

```json
{
  "mcpServers": {
    "mapkg": {
      "command": "/ABS/PATH/.venv/bin/mapkg",
      "args": ["serve"],
      "env": {
        "MAPKG_DATA": "/ABS/PATH/data/sample_mumbai.geojson",
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

**Claude Code:** `claude mcp add mapkg -e MAPKG_DATA=/ABS/PATH/data/sample_mumbai.geojson -- /ABS/PATH/.venv/bin/mapkg serve`

Tools: `ask_map(question)`, `run_sparql(query)`, `find_nearby(lat, lon, radius_m, kind)`, `describe_dataset()`;
resource `mapkg://schema`. When Claude is the MCP client it can also skip `ask_map`, read `describe_dataset`,
and write the SPARQL itself with `run_sparql`.

## Real OpenStreetMap data

The bundled `data/sample_mumbai.geojson` is **illustrative**: landmark/road/park positions are approximate
and everything named "Sample …" is synthetic. For real data (needs internet):

```bash
mapkg fetch --bbox 19.05 72.80 19.15 72.90 --out data/mumbai_west.geojson   # south west north east
export MAPKG_DATA=data/mumbai_west.geojson
mapkg ask "hospitals within 2 km of Bandra"
mapkg build --out data/mumbai_west.ttl     # optional: cache the graph; --data accepts .ttl too
```

Any GeoJSON whose feature properties are OSM tags works (e.g. exports from overpass-turbo or `osmtogeojson`).

## Graph model

```turtle
osm:node/123 a geo:Feature, mk:Feature ;
    rdfs:label "Juhu Beach" ;
    mk:category "natural" ; mk:kind "beach" ; mk:geometryType "Point" ;
    osmt:natural "beach" ;                       # every OSM tag is kept as osmt:<key>
    mk:lengthMeters 3662.3 ;                     # lines only      (mk:areaSqMeters for polygons)
    geo:hasGeometry <.../geom> .
<.../geom> a geo:Geometry ; geo:asWKT "POINT (72.8265 19.0988)"^^geo:wktLiteral .
```

rdflib has no GeoSPARQL support, so `geosparql.py` registers `geof:distance` (metres, via a local azimuthal
projection), `geof:sfWithin`, `geof:sfContains`, `geof:sfIntersects`.

## Design notes

* **The LLM never touches the data directly.** Its output is just a query; `MapStore.validate` parses it and
  accepts only `SELECT`/`ASK` with no `SERVICE` clause (no updates, no outbound requests), and results are row-capped.
* **Self-repair loop.** Parse/execute errors go back to the model as a follow-up message (max 2 retries).
* **Schema-grounded prompting.** The system prompt is generated from the loaded graph (kinds with counts, feature
  names, vocabulary, spatial functions, few-shot examples), so it adapts to whatever dataset you load.
* **Prompt-injection posture.** The question is treated as untrusted data; safety comes from the read-only validator
  rather than from trusting the prompt.

## Known limitations

* Spatial filters scan candidate pairs (no spatial index inside SPARQL), fine for city-sized extracts, slow for
  country-sized ones. Next step: bbox pre-filtering or a GeoSPARQL-capable store (Oxigraph/GraphDB/Jena).
* No query timeout (rdflib can't interrupt a running query); keep extracts bounded.
* Overpass conversion handles nodes and ways only (no multipolygon relations).
* The rule-based translator is deliberately small; it's a fallback, not a parser for arbitrary English.

## Layout

```
src/mapkg/  ontology.py builder.py geosparql.py store.py schema.py llm.py rules.py assistant.py overpass.py server.py cli.py
tests/      graph · geosparql · store safety · rules · LLM (fake client) · overpass · MCP server
data/       sample_mumbai.geojson
```
