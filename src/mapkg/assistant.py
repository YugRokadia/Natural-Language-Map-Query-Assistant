"""NL question -> SPARQL -> results. Uses the LLM when available, rules otherwise."""

from __future__ import annotations

import os

from .llm import LLMTranslator, Translation, TranslationError
from .rules import RuleBasedTranslator
from .store import MapStore, QueryRejected


class MapAssistant:
    """engine: "auto" (LLM if ANTHROPIC_API_KEY is set, else rules), "llm", or "rules"."""

    def __init__(self, store: MapStore, engine: str | None = None, llm: LLMTranslator | None = None):
        self.store = store
        self.engine = (engine or os.environ.get("MAPKG_ENGINE", "auto")).lower()
        self.rules = RuleBasedTranslator(store)
        self.llm = llm
        if self.llm is None and self.engine in ("auto", "llm") and (
            self.engine == "llm" or os.environ.get("ANTHROPIC_API_KEY")
        ):
            self.llm = LLMTranslator(store)

    def ask(self, question: str) -> Translation:
        question = question.strip()
        if not question:
            raise TranslationError("Empty question.")
        if self.llm is not None and self.engine != "rules":
            try:
                return self.llm.translate(question)
            except Exception as exc:  # API/network errors, or invalid queries after retries
                if self.engine == "llm":
                    raise
                try:
                    t = self.rules.translate(question)
                except (TranslationError, QueryRejected):
                    raise TranslationError(f"LLM failed ({exc}) and no rule matched.") from exc
                t.note += f" (LLM unavailable: {type(exc).__name__})"
                return t
        return self.rules.translate(question)
