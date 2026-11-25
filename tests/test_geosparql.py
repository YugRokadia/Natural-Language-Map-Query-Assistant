import pytest

POLY = "POLYGON((0 0,0 2,2 2,2 0,0 0))"


def val(store, expr):
    return store.execute(f"SELECT ({expr} AS ?v) WHERE {{}}").rows[0]["v"]


def test_distance_is_metres(store):
    # 0.01 degrees of latitude is ~1105 m
    d = val(store, 'geof:distance("POINT(72.80 19.00)", "POINT(72.80 19.01)")')
    assert 1100 < d < 1115


def test_distance_accepts_units_arg_and_crs_prefix(store):
    crs = "<http://www.opengis.net/def/crs/EPSG/0/4326> POINT(72.80 19.00)"
    d = val(store, f'geof:distance("{crs}", "POINT(72.80 19.01)", "m")')
    assert 1100 < d < 1115


@pytest.mark.parametrize("fn,a,b,expected", [
    ("sfWithin", "POINT(1 1)", POLY, True),
    ("sfWithin", "POINT(5 5)", POLY, False),
    ("sfContains", POLY, "POINT(1 1)", True),
    ("sfIntersects", "LINESTRING(-1 1, 3 1)", POLY, True),
    ("sfIntersects", "POINT(9 9)", POLY, False),
])
def test_topological_predicates(store, fn, a, b, expected):
    assert val(store, f'geof:{fn}("{a}", "{b}")') is expected
