from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
from scipy.spatial import cKDTree
from shapely.geometry.base import BaseGeometry


@dataclass(frozen=True, slots=True)
class LocatedService:
    category: str
    name: str | None
    graph_node_id: int
    geometry: BaseGeometry


@dataclass(frozen=True, slots=True)
class ServiceLoadResult:
    nodes_by_category: dict[str, list[int]]
    services_by_category: dict[str, list[LocatedService]]

    def organizer_data(self) -> dict[str, list[list]]:
        return {
            category: [
                [service.name, service.graph_node_id, service.geometry]
                for service in services
            ]
            for category, services in self.services_by_category.items()
        }


def _run_osmium(arguments: list[str]) -> None:
    try:
        subprocess.run(
            ["osmium", *arguments],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise RuntimeError("osmium-tool is required to extract OSM services") from error
    except subprocess.CalledProcessError as error:
        message = error.stderr.strip() or error.stdout.strip() or str(error)
        raise RuntimeError(f"osmium failed: {message}") from error


def categorize_services(
    services_geojson: gpd.GeoDataFrame,
    service_categories: dict[str, list[tuple[str, str]]],
) -> dict[str, list[tuple[str | None, BaseGeometry]]]:
    """Group OSM features under domain categories without dropping duplicate names."""
    categorized_services = {}
    for category_code, osm_tags in service_categories.items():
        category_mask = np.zeros(len(services_geojson), dtype=bool)
        for osm_key, osm_value in osm_tags:
            if osm_key in services_geojson.columns:
                category_mask |= (
                    services_geojson[osm_key].eq(osm_value).fillna(False).to_numpy()
                )

        category_services = services_geojson.loc[category_mask]
        if category_services.empty:
            categorized_services[category_code] = []
            continue

        points = category_services.geometry.representative_point()
        if "name" in category_services.columns:
            names = [
                value.strip() if isinstance(value, str) and value.strip() else None
                for value in category_services["name"]
            ]
        else:
            names = [None] * len(category_services)
        categorized_services[category_code] = list(zip(names, points))
    return categorized_services


def snap_services_to_graph(
    graph: nx.MultiDiGraph,
    categorized_services: dict[str, list[tuple[str | None, BaseGeometry]]],
) -> ServiceLoadResult:
    """Associate every categorized service with its nearest walking-graph node."""
    graph_crs = graph.graph.get("crs")
    if graph_crs is not None:
        if ox.projection.is_projected(graph_crs):
            projected_graph = graph
        else:
            projected_graph = ox.project_graph(graph)
        target_crs = projected_graph.graph["crs"]
    else:
        projected_graph = graph
        target_crs = None

    node_ids = list(projected_graph.nodes)
    if not node_ids:
        raise ValueError("cannot snap services to an empty graph")
    node_coordinates = np.asarray(
        [
            (projected_graph.nodes[node]["x"], projected_graph.nodes[node]["y"])
            for node in node_ids
        ]
    )
    tree = cKDTree(node_coordinates)

    nodes_by_category = {}
    services_by_category = {}
    for category, services in categorized_services.items():
        if not services:
            nodes_by_category[category] = []
            services_by_category[category] = []
            continue

        geometries = [geometry for _name, geometry in services]
        if target_crs is not None:
            projected_points = gpd.GeoSeries(geometries, crs="EPSG:4326").to_crs(
                target_crs
            )
            coordinates = np.asarray(
                [(geometry.x, geometry.y) for geometry in projected_points]
            )
        else:
            coordinates = np.asarray(
                [(geometry.x, geometry.y) for geometry in geometries]
            )
        _distances, indices = tree.query(coordinates, k=1)

        located = [
            LocatedService(
                category=category,
                name=name,
                graph_node_id=int(node_ids[int(node_index)]),
                geometry=geometry,
            )
            for (name, geometry), node_index in zip(services, indices, strict=True)
        ]
        services_by_category[category] = located
        nodes_by_category[category] = [service.graph_node_id for service in located]

    return ServiceLoadResult(
        nodes_by_category=nodes_by_category,
        services_by_category=services_by_category,
    )


def load_services_from_pbf(
    graph: nx.MultiDiGraph,
    region_pbf_path: str | Path,
    service_categories: dict[str, list[tuple[str, str]]],
) -> ServiceLoadResult:
    if not service_categories:
        raise ValueError("at least one service category must be configured")

    pbf_path = Path(region_pbf_path).resolve()
    if not pbf_path.is_file():
        raise FileNotFoundError(f"region PBF file not found: {pbf_path}")

    filters = [
        f"nwr/{key}={value}"
        for tags in service_categories.values()
        for key, value in tags
    ]
    with tempfile.TemporaryDirectory(prefix="15minute-services-") as temp_dir:
        temp_path = Path(temp_dir)
        services_pbf = temp_path / "services.osm.pbf"
        services_geojson = temp_path / "services.geojson"
        _run_osmium(
            [
                "tags-filter",
                str(pbf_path),
                *filters,
                "-o",
                str(services_pbf),
                "--overwrite",
            ]
        )
        _run_osmium(
            [
                "export",
                str(services_pbf),
                "-o",
                str(services_geojson),
                "--overwrite",
            ]
        )
        frame = gpd.read_file(services_geojson)

    categorized = categorize_services(frame, service_categories)
    return snap_services_to_graph(graph, categorized)
