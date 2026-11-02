"""Tests of the all-cities summary used by the Brazil map."""

from fifteen_minute_city.api.app import app
from fifteen_minute_city.api.service import coverage_from_masks

HEALTH, CULTURE = 1 << 1, 1 << 4


def test_coverage_from_masks_requires_every_selected_category():
    masks = {0: 10.0, HEALTH: 20.0, CULTURE: 30.0, HEALTH | CULTURE: 40.0}

    assert coverage_from_masks(masks, HEALTH) == (100.0, 60.0, 60.0)
    assert coverage_from_masks(masks, CULTURE) == (100.0, 70.0, 70.0)
    assert coverage_from_masks(masks, HEALTH | CULTURE) == (100.0, 40.0, 40.0)


def test_coverage_from_masks_without_population():
    assert coverage_from_masks({}, HEALTH) == (0, 0, None)


def test_summary_routes_are_not_captured_by_city_id():
    paths = list(app.openapi()["paths"])

    assert "/api/v1/cities/summary" in paths
    assert "/api/v1/cities/boundaries" in paths
    assert paths.index("/api/v1/cities/summary") < paths.index(
        "/api/v1/cities/{city_id}"
    )
