from types import SimpleNamespace

import pytest

from mapkg.assistant import MapAssistant
from mapkg.llm import LLMTranslator, TranslationError, extract_sparql

GOOD = '```sparql\nSELECT (COUNT(?f) AS ?count) WHERE { ?f mk:kind "hospital" }\n```'
BAD = "```sparql\nSELECT ?x WHERE { ?x mk:kind \n```"  # syntax error


class FakeClient:
    """Mimics anthropic.Anthropic().messages.create, replaying scripted replies."""

    def __init__(self, replies):
        self.replies, self.calls = list(replies), []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        if isinstance(self.replies[0], Exception):
            raise self.replies.pop(0)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.replies.pop(0))])


def test_extract_sparql_variants():
    assert extract_sparql("```sparql\nASK { ?s ?p ?o }\n```") == "ASK { ?s ?p ?o }"
    assert extract_sparql("```\nASK { ?s ?p ?o }\n```") == "ASK { ?s ?p ?o }"
    assert extract_sparql("ASK { ?s ?p ?o }") == "ASK { ?s ?p ?o }"


def test_happy_path_and_prompt_contents(store):
    client = FakeClient([GOOD])
    t = LLMTranslator(store, client=client).translate("how many hospitals?")
    assert t.engine == "llm" and t.attempts == 1 and t.result.rows == [{"count": 4}]
    system = client.calls[0]["system"]
    assert "geof:distance" in system and "Lilavati Hospital" in system and "40 features" in system


def test_invalid_query_is_fed_back_and_retried(store):
    client = FakeClient([BAD, GOOD])
    t = LLMTranslator(store, client=client).translate("how many hospitals?")
    assert t.attempts == 2
    retry_msgs = client.calls[1]["messages"]
    assert retry_msgs[-1]["role"] == "user" and "rejected or failed" in retry_msgs[-1]["content"]


def test_gives_up_after_max_retries(store):
    with pytest.raises(TranslationError):
        LLMTranslator(store, client=FakeClient([BAD, BAD, BAD]), max_retries=2).translate("x")


def test_llm_cannot_smuggle_updates(store):
    evil = "```sparql\nINSERT DATA { <urn:a> <urn:b> <urn:c> }\n```"
    before = len(store.graph)
    with pytest.raises(TranslationError):
        LLMTranslator(store, client=FakeClient([evil, evil, evil])).translate("x")
    assert len(store.graph) == before


def test_auto_engine_falls_back_to_rules_when_llm_errors(store):
    llm = LLMTranslator(store, client=FakeClient([RuntimeError("network down")]))
    t = MapAssistant(store, engine="auto", llm=llm).ask("how many hospitals are there?")
    assert t.engine == "rules" and "LLM unavailable" in t.note and t.result.rows == [{"count": 4}]


def test_forced_llm_engine_propagates_errors(store):
    llm = LLMTranslator(store, client=FakeClient([RuntimeError("network down")]))
    with pytest.raises(RuntimeError):
        MapAssistant(store, engine="llm", llm=llm).ask("anything")
