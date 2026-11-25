import pytest

from mapkg.assistant import MapAssistant
from mapkg.llm import TranslationError


@pytest.fixture(scope="module")
def ask(store):
    a = MapAssistant(store, engine="rules")
    return lambda q: a.ask(q).result.rows


def names(rows):
    return [r["name"] for r in rows]


def test_near_with_radius_km(ask):
    rows = ask("Which cafes are within 1 km of NMIMS?")
    assert names(rows) == ["Sample Cafe VP1", "Sample Cafe VP2", "Sample Cafe VP3"]
    assert [r["distance_m"] for r in rows] == sorted(r["distance_m"] for r in rows)


def test_radius_in_metres_excludes_far_results(ask):
    assert names(ask("cafes within 200 m of NMIMS Mumbai Campus")) == ["Sample Cafe VP1"]


def test_nearest_returns_single_closest(ask):
    assert names(ask("nearest pharmacy to NMIMS Mumbai Campus")) == ["Sample Pharmacy 1"]


def test_top_n_closest(ask):
    assert len(ask("2 closest cafes to Gateway of India")) == 2


def test_count(ask):
    assert ask("How many hospitals are there?") == [{"count": 4}]
    assert ask("how many cafes within 2 km of Vile Parle") == [{"count": 3}]


def test_distance_between_places(ask):
    (row,) = ask("distance between Dadar and Bandra")
    assert 3900 < row["distance_m"] < 4200


def test_superlatives(ask):
    assert names(ask("largest park")) == ["Oval Maidan"]
    assert names(ask("longest road")) == ["Western Express Highway"]


def test_place_name_containing_a_kind_word_is_not_a_kind(ask):
    # "Park" inside "Sanjay Gandhi National Park" must not be read as place type "park"
    assert ask("what is inside Sanjay Gandhi National Park") == []
    assert "Churchgate" in names(ask("what is inside Oval Maidan"))


def test_lookup_by_name(ask):
    assert ask("tell me about Powai Lake")[0]["geometry_type"] == "Polygon"


def test_nonsense_raises(store):
    with pytest.raises(TranslationError):
        MapAssistant(store, engine="rules").ask("qwerty asdf")
