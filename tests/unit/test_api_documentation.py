"""Ensure the manual tracks the published HTTP contract."""

import re
from pathlib import Path

from fifteen_minute_city.api.app import app
from fifteen_minute_city.api.service import (
    CATEGORY_METRICS,
    OVERALL_METRICS,
    PUBLIC_STRATEGIES,
)

MANUAL = Path(__file__).resolve().parents[2] / "docs" / "API.md"


def test_api_manual_documents_every_get_endpoint() -> None:
    text = MANUAL.read_text(encoding="utf-8")
    documented = set(re.findall(r"^\| `GET (/[^`]+)`", text, flags=re.MULTILINE))
    actual = {
        route.path
        for route in app.routes
        if "GET" in (getattr(route, "methods", None) or set())
        and (route.path == "/health" or route.path.startswith("/api/v1/"))
    }
    assert actual <= documented, (
        f"Missing endpoints in docs/API.md: {sorted(actual - documented)}"
    )


def test_api_manual_lists_all_public_metrics_and_strategies() -> None:
    text = MANUAL.read_text(encoding="utf-8")
    for metric in CATEGORY_METRICS | OVERALL_METRICS:
        assert f"`{metric}`" in text, f"Undocumented API metric: {metric}"
    for strategy in PUBLIC_STRATEGIES:
        assert f"`{strategy}`" in text, f"Undocumented public strategy: {strategy}"


def test_api_manual_contains_only_chapters_4_to_7() -> None:
    text = MANUAL.read_text(encoding="utf-8")
    chapters = re.findall(r"^## ([0-9]+)\.", text, flags=re.MULTILINE)
    assert chapters == ["4", "5", "6", "7"]
