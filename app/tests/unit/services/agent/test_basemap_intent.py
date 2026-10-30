from __future__ import annotations

import pytest

from server.services.agent.basemap_intent import (
    basemap_descriptions,
    match_requested_basemap,
)

BASEMAPS = [
    {"id": "osm_default", "metadata": {"label": "OpenStreetMap", "keywords": ["street"]}},
    {
        "id": "esri_world_imagery",
        "metadata": {"label": "Satellite Imagery", "keywords": ["satellite", "aerial"]},
    },
    {"id": "osm_dark", "metadata": {"label": "Dark Basemap", "keywords": ["dark", "night"]}},
    {"id": "positron", "metadata": {"label": "Positron", "keywords": ["light", "clean"]}},
]

###############################################################################
@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Show Sanremo in satellite view", "esri_world_imagery"),
        ("an aerial map of Turin", "esri_world_imagery"),
        ("night map of Rome", "osm_dark"),
        ("satellite but dark please", None),
        ("show the light rail stations", None),
        ("show me a street map", None),
        ("show Sanremo", None),
    ],
)
def test_match_requested_basemap(message: str, expected: str | None) -> None:
    assert match_requested_basemap(message, BASEMAPS) == expected

###############################################################################
def test_basemap_descriptions_carry_label_and_keywords() -> None:
    assert basemap_descriptions(BASEMAPS)["esri_world_imagery"] == (
        "Satellite Imagery (satellite, aerial)"
    )
