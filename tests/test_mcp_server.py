import asyncio

import pytest

from mapkg.assistant import MapAssistant
from mapkg.server import create_server


@pytest.fixture(scope="module")
def server(store):
    return create_server(store, MapAssistant(store, engine="rules"))


def run(coro):
    return asyncio.run(coro)


def test_tools_are_registered(server):
    names = {t.name for t in run(server.list_tools())}
    assert {"describe_dataset", "ask_map", "run_sparql", "find_nearby"} <= names


def _payload(result):
    """Normalise v1/v2 call_tool return shapes to a dict."""
    import json

    if isinstance(result, tuple):  # v1: (content, structured)
        result = result[1] if isinstance(result[1], dict) else result[0]
    if isinstance(result, dict):
        return result.get("result", result)
    structured = getattr(result, "structured_content", None)
    if structured:
        return structured.get("result", structured)
    content = result if isinstance(result, list) else result.content
    return json.loads(content[0].text)


def test_ask_map_tool(server):
    out = _payload(run(server.call_tool("ask_map", {"question": "nearest pharmacy to NMIMS Mumbai Campus"})))
    assert out["rows"][0]["name"] == "Sample Pharmacy 1" and "SELECT" in out["sparql"]


def test_find_nearby_tool(server):
    out = _payload(run(server.call_tool("find_nearby", {"lat": 19.1004, "lon": 72.8365, "radius_m": 200, "kind": "cafe"})))
    assert [r["name"] for r in out["rows"]] == ["Sample Cafe VP1"]


def test_run_sparql_tool_reports_errors_instead_of_raising(server):
    out = _payload(run(server.call_tool("run_sparql", {"query": "DROP ALL"})))
    assert "error" in out
