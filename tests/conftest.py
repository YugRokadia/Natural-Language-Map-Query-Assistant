from pathlib import Path

import pytest

from mapkg import MapStore

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample_mumbai.geojson"


@pytest.fixture(scope="session")
def store() -> MapStore:
    return MapStore.from_geojson(SAMPLE)
