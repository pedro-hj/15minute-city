"""Validate hypothetical essential-service locations supplied as GeoJSON."""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import isfinite
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point

MAX_SCENARIO_BYTES = 2_000_000
MAX_SCENARIO_SERVICES = 200


@dataclass(frozen=True, slots=True)
class HypotheticalService:
    category: str
    name: str | None
    point: Point


def load_service_scenario(
    path: str | Path,
    *,
    boundary: gpd.GeoDataFrame,
    categories: set[str],
) -> list[HypotheticalService]:
    """Accept only Point features inside the selected municipality in WGS84."""
    file_path = Path(path).expanduser().resolve()
    if not file_path.is_file():
        raise FileNotFoundError(f"Scenario GeoJSON not found: {file_path}")
    if file_path.stat().st_size > MAX_SCENARIO_BYTES:
        raise ValueError("Scenario GeoJSON exceeds the 2 MB limit")
    try:
        content = json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Scenario must be a valid UTF-8 GeoJSON file") from exc

    if not isinstance(content, dict) or content.get("type") != "FeatureCollection":
        raise ValueError("Scenario must be a GeoJSON FeatureCollection")
    if content.get("crs") is not None:
        raise ValueError(
            "Scenario must use GeoJSON WGS84 coordinates without a CRS override"
        )
    features = content.get("features")
    if (
        not isinstance(features, list)
        or not 1 <= len(features) <= MAX_SCENARIO_SERVICES
    ):
        raise ValueError("Scenario must contain 1 to 200 Point features")
    if boundary.empty or boundary.crs is None:
        raise ValueError("Municipality boundary is missing or has no CRS")
    geometry = boundary.to_crs("EPSG:4326").geometry.union_all()

    services: list[HypotheticalService] = []
    for index, feature in enumerate(features, start=1):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError(f"Feature {index} must be a GeoJSON Feature")
        properties = feature.get("properties")
        location = feature.get("geometry")
        if not isinstance(properties, dict) or not isinstance(location, dict):
            raise TypeError(f"Feature {index} requires properties and geometry")
        category = properties.get("category")
        if not isinstance(category, str) or category not in categories:
            raise ValueError(
                f"Feature {index} has an unsupported or unselected category: {category!r}"
            )
        name = properties.get("name")
        if name is not None and (
            not isinstance(name, str) or not 1 <= len(name.strip()) <= 120
        ):
            raise ValueError(
                f"Feature {index} name must be a nonempty string of at most 120 characters"
            )
        if location.get("type") != "Point":
            raise ValueError(f"Feature {index} must use Point geometry")
        coordinates = location.get("coordinates")
        if (
            not isinstance(coordinates, list)
            or len(coordinates) != 2
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                for value in coordinates
            )
        ):
            raise ValueError(f"Feature {index} requires numeric [longitude, latitude]")
        longitude, latitude = coordinates
        if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
            raise ValueError(f"Feature {index} has coordinates outside WGS84 bounds")
        point = Point(longitude, latitude)
        if not geometry.covers(point):
            raise ValueError(f"Feature {index} is outside the municipality boundary")
        services.append(
            HypotheticalService(
                category=category,
                name=name.strip() if name is not None else None,
                point=point,
            )
        )
    return services
