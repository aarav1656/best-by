"""Fixtures built from real captured API responses. No invented data.

Every recall these tests assert against is a real openFDA food enforcement
report in `data/fda_food_enforcement_2025_2026.json`, captured 2026-09-14 from
https://api.fda.gov/food/enforcement.json. A test that passes against a fixture
someone wrote to make it pass proves nothing about the feed, and the feed is the
only thing this system reads.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.feeds.openfda import load_captured
from agent.shelf import load_pantry

ROOT = Path(__file__).parent.parent
CORPUS = ROOT / "data" / "fda_food_enforcement_2025_2026.json"


@pytest.fixture(scope="session")
def recalls():
    return load_captured(str(CORPUS))


@pytest.fixture(scope="session")
def by_number(recalls):
    return {r.recall_number: r for r in recalls}


@pytest.fixture(scope="session")
def pantry():
    return load_pantry(ROOT / "data" / "pantry.json")


@pytest.fixture(scope="session")
def lots(pantry):
    return {l.lot_id: l for l in pantry.lots}
