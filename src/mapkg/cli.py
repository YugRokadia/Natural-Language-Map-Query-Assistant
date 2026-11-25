"""Command-line interface:  mapkg build | schema | sparql | ask | serve | fetch"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .store import MapStore, QueryRejected, QueryResult


def _table(res: QueryResult) -> str:
    if res.boolean is not None:
        return str(res.boolean)
    if not res.rows:
        return "(no results)"
    widths = [max(len(c), *(len(str(r[c])) for r in res.rows)) for c in res.columns]
    line = "  ".join(c.ljust(w) for c, w in zip(res.columns, widths))
    out = [line, "  ".join("-" * w for w in widths)]
    out += ["  ".join(str(r[c]).ljust(w) for c, w in zip(res.columns, widths)) for r in res.rows]
    if res.truncated:
        out.append("... (truncated)")
    return "\n".join(out)


def _data_path(arg: str | None) -> Path:
    from .server import default_data_path

    return Path(arg) if arg else default_data_path()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mapkg", description=__doc__)
    ap.add_argument("--data", help="GeoJSON or Turtle file (default: $MAPKG_DATA or the bundled Mumbai sample)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="convert GeoJSON to an RDF Turtle file")
    b.add_argument("--out", default="graph.ttl")
    sub.add_parser("schema", help="print the schema/prompt summary")
    s = sub.add_parser("sparql", help="run a SPARQL query")
    s.add_argument("query", help="query text, or @file.rq")
    a = sub.add_parser("ask", help="ask a question in natural language")
    a.add_argument("question")
    a.add_argument("--engine", choices=["auto", "llm", "rules"], default=None)
    a.add_argument("--json", action="store_true", help="print JSON instead of a table")
    sub.add_parser("serve", help="start the MCP server (stdio)")
    f = sub.add_parser("fetch", help="download real OSM data from Overpass (needs internet)")
    f.add_argument("--bbox", nargs=4, type=float, metavar=("SOUTH", "WEST", "NORTH", "EAST"), required=True)
    f.add_argument("--out", required=True)

    args = ap.parse_args(argv)

    if args.cmd == "fetch":
        from . import overpass

        data = overpass.to_geojson(overpass.fetch(overpass.build_query(*args.bbox)))
        Path(args.out).write_text(json.dumps(data), encoding="utf-8")
        print(f"Wrote {len(data['features'])} features to {args.out}")
        return 0

    path = _data_path(args.data)
    if args.cmd == "serve":
        from .server import main as serve

        serve(path)
        return 0

    store = MapStore.load(path)
    try:
        if args.cmd == "build":
            store.save(args.out)
            print(f"Wrote {len(store.graph)} triples ({store.feature_count()} features) to {args.out}")
        elif args.cmd == "schema":
            from .schema import schema_summary

            print(schema_summary(store))
        elif args.cmd == "sparql":
            q = Path(args.query[1:]).read_text() if args.query.startswith("@") else args.query
            print(_table(store.execute(q)))
        elif args.cmd == "ask":
            from .assistant import MapAssistant

            t = MapAssistant(store, engine=args.engine).ask(args.question)
            if args.json:
                print(json.dumps(t.to_dict(), indent=2))
            else:
                print(f"[{t.engine}] {t.note}\n\n{t.sparql}\n\n{_table(t.result)}")
    except Exception as exc:  # user-facing errors, not tracebacks
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
