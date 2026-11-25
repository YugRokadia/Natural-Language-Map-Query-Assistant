"""Deterministic, offline question -> SPARQL translator.

Handles the common spatial question shapes so the project works (and is testable)
without an API key. The LLM translator covers everything else.

Supported shapes (kinds/names are discovered from the loaded graph):
    list / show        "show all cafes", "list hospitals"
    count              "how many pharmacies are there", "how many cafes within 1 km of NMIMS"
    near               "hospitals within 3 km of Bandra", "restaurants near Gateway of India"
    nearest            "nearest pharmacy to NMIMS Mumbai Campus", "3 closest cafes to Dadar"
    distance           "distance between Dadar and Bandra", "how far is Juhu Beach from Vile Parle"
    superlative        "largest park", "longest road"
    containment        "what is inside Sanjay Gandhi National Park"
"""

from __future__ import annotations

import re

from .llm import Translation, TranslationError
from .store import MapStore

_EXTRA_SYNONYMS = {
    "cafe": ["cafes", "café", "cafés", "coffee shop", "coffee shops"],
    "pharmacy": ["pharmacies", "chemist", "chemists", "drugstore", "drugstores"],
    "hospital": ["hospitals", "clinic", "clinics"],
    "station": ["stations", "railway station", "railway stations", "train station", "train stations"],
    "university": ["universities", "college", "colleges", "campus"],
    "park": ["parks", "garden", "gardens", "maidan"],
    "place_of_worship": ["temple", "temples", "mosque", "mosques", "place of worship", "places of worship"],
    "aerodrome": ["airport", "airports"],
    "atm": ["atms", "cash machine", "cash machines"],
    "beach": ["beaches"],
    "museum": ["museums"],
    "restaurant": ["restaurants"],
    "school": ["schools"],
}
_ROAD_WORDS = ["roads", "road", "highways", "highway", "streets", "street", "bridges", "bridge"]
_STOP = set("""the a an of to from in on at near nearby around within inside by me my us is are was were be there
 what which where who how many much show list find give tell all any some closest nearest next far distance between
 and or than with for do does can i you please map km kilometer kilometers kilometre kilometres m meter meters metre
 metres away largest biggest longest smallest shortest top tell about describe info information details""".split())
_DIST = re.compile(r"(\d+(?:\.\d+)?)\s*(km|kilometers?|kilometres?|m|meters?|metres?)\b")
_TOPN = re.compile(r"\b(\d+)\s+(?:nearest|closest)\b|\b(?:nearest|closest)\s+(\d+)\b")


def _q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


class RuleBasedTranslator:
    def __init__(self, store: MapStore, max_rows: int = 100):
        self.store = store
        self.max_rows = max_rows
        self.labels = store.labels()
        self.kinds: dict[str, tuple[str, str]] = {}  # phrase -> (category, kind)
        for cat, kind, _ in store.kind_counts():
            base = kind.replace("_", " ")
            for phrase in {base, base + "s", base + "es", *_EXTRA_SYNONYMS.get(kind, [])}:
                self.kinds.setdefault(phrase, (cat, kind))

    # ---- parsing helpers ----
    def _find_kind(self, text: str):
        for phrase in sorted(self.kinds, key=len, reverse=True):
            if re.search(rf"\b{re.escape(phrase)}\b", text):
                return phrase, self.kinds[phrase]
        for w in _ROAD_WORDS:
            if re.search(rf"\b{w}\b", text):
                return w, ("highway", None)
        return None, None

    def _extract_labels(self, text: str) -> tuple[str, list[tuple[int, str]]]:
        """Find full place names in the text; blank them out (same length) so their words
        (e.g. the 'park' in 'National Park') aren't mistaken for the place type."""
        hits: list[tuple[int, str]] = []
        norm = text.replace(".", "")
        for lbl in sorted(self.labels, key=len, reverse=True):
            l = lbl.lower().replace(".", "")
            if len(l) < 3:
                continue
            m = re.search(rf"(?<!\w){re.escape(l)}(?!\w)", norm)
            if m:
                hits.append((m.start(), lbl))
                norm = norm[:m.start()] + "|" + " " * (m.end() - m.start() - 1) + norm[m.end():]
        return norm, hits

    def _find_anchors(self, text: str, kind_phrase: str | None) -> list[tuple[int, str]]:
        t = text
        if kind_phrase:
            t = re.sub(rf"\b{re.escape(kind_phrase)}\b", " | ", t)
        t = _DIST.sub(" | ", t)
        tokens = re.findall(r"[\w.'&-]+|\|", t)
        segments, cur = [], []
        for tok in tokens:
            if tok == "|" or tok in _STOP or tok.isdigit():
                if cur:
                    segments.append(cur)
                cur = []
            else:
                cur.append(tok)
        if cur:
            segments.append(cur)

        lower = {lbl.lower().replace(".", ""): lbl for lbl in self.labels}
        found: list[tuple[int, str]] = []
        for seg in segments:
            phrase = " ".join(seg).replace(".", "")
            hit = lower.get(phrase)
            if not hit:  # substring match, prefer the shortest (most specific) label
                cands = sorted((l for k, l in lower.items() if phrase in k), key=len)
                hit = cands[0] if cands else None
            if hit and hit not in [h for _, h in found]:
                found.append((text.find(seg[0].replace(".", "")), hit))
        return found

    # ---- SPARQL builders ----
    @staticmethod
    def _kind_pattern(cat, kind, var="?f") -> str:
        if cat is None and kind is None:
            return ""
        if kind:
            return f"{var} mk:kind {_q(kind)} ."
        return f"{var} mk:category {_q(cat)} ."

    def _build(self, question: str) -> tuple[str, str]:
        text = question.lower().strip().rstrip("?.! ")
        stripped, label_hits = self._extract_labels(text)
        kphrase, kmatch = self._find_kind(stripped)
        fuzzy = [h for h in self._find_anchors(stripped, kphrase) if h[1] not in [l for _, l in label_hits]]
        anchors = [lbl for _, lbl in sorted(label_hits + fuzzy)]
        dm = _DIST.search(text)
        radius_m = None
        if dm:
            val = float(dm.group(1))
            radius_m = val * 1000 if dm.group(2).startswith("k") else val
        cat, kind = kmatch or (None, None)
        anchor_bits = lambda a: (  # noqa: E731
            f"?anchor rdfs:label {_q(a)} ; geo:hasGeometry/geo:asWKT ?wkt0 ."
        )

        # distance between two named places
        if ("distance" in text or "how far" in text) and len(anchors) >= 2:
            a, b = anchors[:2]
            return ("SELECT ?from ?to (ROUND(geof:distance(?wa, ?wb)) AS ?distance_m) WHERE {\n"
                    f"  ?a rdfs:label {_q(a)} ; geo:hasGeometry/geo:asWKT ?wa .\n"
                    f"  ?b rdfs:label {_q(b)} ; geo:hasGeometry/geo:asWKT ?wb .\n"
                    f"  BIND({_q(a)} AS ?from) BIND({_q(b)} AS ?to)\n}}"), "distance between two places"

        # superlatives
        sup = re.search(r"\b(largest|biggest|longest|smallest|shortest)\b", text)
        if sup and kmatch:
            lines = cat == "highway"
            prop = "mk:lengthMeters" if lines else "mk:areaSqMeters"
            order = "DESC" if sup.group(1) in ("largest", "biggest", "longest") else "ASC"
            alias = "length_m" if lines else "area_sqm"
            return (f"SELECT ?name ?{alias} WHERE {{\n  {self._kind_pattern(cat, kind)}\n"
                    f"  ?f rdfs:label ?name ; {prop} ?{alias} .\n}} ORDER BY {order}(?{alias}) LIMIT 1"), \
                   f"{sup.group(1)} {kphrase}"

        if not kmatch and not anchors:
            raise TranslationError("I couldn't recognise a place type or a place name in that question.")

        count = text.startswith("how many") or " number of " in f" {text} "
        sel = "(COUNT(DISTINCT ?f) AS ?count)" if count else \
              "?name ?kind (ROUND(geof:distance(?wkt, ?wkt0)) AS ?distance_m)"

        # relative to a named anchor
        if anchors and (kmatch or not ("distance" in text or "how far" in text)) and not (not kmatch and len(anchors) == 1 and not re.search(r"\b(near|nearby|around|within|inside|in|close)\b", text)):
            a = anchors[0]
            kphrase = kphrase or "features"
            nearest = re.search(r"\b(nearest|closest)\b", text)
            tn = _TOPN.search(text)
            limit = int(next(g for g in tn.groups() if g)) if tn else (1 if nearest else 50)
            anchor_geom_poly = bool(self.store.execute(
                f"ASK {{ ?a rdfs:label {_q(a)} ; mk:geometryType ?t . FILTER(CONTAINS(?t, 'Polygon')) }}"
            ).boolean)
            contain = (not dm and not nearest and anchor_geom_poly
                       and re.search(r"\b(in|inside|within)\b", text))
            if contain:
                cond = "geof:sfWithin(?wkt, ?wkt0)"
                sel_c = "(COUNT(DISTINCT ?f) AS ?count)" if count else "?name ?kind"
                return (f"SELECT {sel_c} WHERE {{\n  {anchor_bits(a)}\n  {self._kind_pattern(cat, kind)}\n"
                        f"  ?f rdfs:label ?name ; geo:hasGeometry/geo:asWKT ?wkt . OPTIONAL {{ ?f mk:kind ?kind }}\n"
                        f"  FILTER(?f != ?anchor && {cond})\n}} LIMIT 50"), f"{kphrase} inside {a}"
            if dm or not nearest:
                radius = radius_m if radius_m is not None else 1000.0
                cond = f"geof:distance(?wkt, ?wkt0) <= {radius:g}"
            else:
                cond = "true"
            tail = "" if count else f"\nORDER BY ?distance_m LIMIT {limit}"
            return (f"SELECT {sel} WHERE {{\n  {anchor_bits(a)}\n  {self._kind_pattern(cat, kind)}\n"
                    f"  ?f rdfs:label ?name ; geo:hasGeometry/geo:asWKT ?wkt . OPTIONAL {{ ?f mk:kind ?kind }}\n"
                    f"  FILTER(?f != ?anchor && {cond})\n}}{tail}"), f"{kphrase} near {a}"

        # a place type on its own
        if kmatch:
            if count:
                return (f"SELECT (COUNT(DISTINCT ?f) AS ?count) WHERE {{ {self._kind_pattern(cat, kind)} }}",
                        f"count of {kphrase}")
            return (f"SELECT ?name ?kind WHERE {{\n  {self._kind_pattern(cat, kind)}\n"
                    f"  ?f mk:kind ?kind . OPTIONAL {{ ?f rdfs:label ?name }}\n}} ORDER BY ?name LIMIT 50"), \
                   f"all {kphrase}"

        # a name on its own: describe it
        a = anchors[0]
        return (f"SELECT ?name ?category ?kind ?geometry_type WHERE {{\n"
                f"  ?f rdfs:label ?name ; mk:geometryType ?geometry_type .\n  FILTER(?name = {_q(a)})\n"
                f"  OPTIONAL {{ ?f mk:category ?category ; mk:kind ?kind }}\n}}"), f"lookup {a}"

    def translate(self, question: str) -> Translation:
        sparql, intent = self._build(question)
        result = self.store.execute(sparql, max_rows=self.max_rows)
        return Translation(question, sparql, result, engine="rules", note=f"rule-based: {intent}")
