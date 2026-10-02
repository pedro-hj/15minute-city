from __future__ import annotations

import logging
import time
from pathlib import Path

import geopandas as gpd
import networkx as nx
import osmnx as ox

from fifteen_minute_city.config import AnalysisSettings
from fifteen_minute_city.constants import SERVICE_CATEGORIES
from fifteen_minute_city.core.modules.algorithms import multi_source_algorithm
from fifteen_minute_city.core.modules.exceptions import ServiceNotSupportedError
from fifteen_minute_city.db.pipelines.algorithm_pipeline import AlgorithmPipeline
from fifteen_minute_city.infrastructure.osm.graph import (
    OSMGraphArtifact,
    load_or_build_osm_graph,
)
from fifteen_minute_city.infrastructure.osm.services import load_services_from_pbf

logger = logging.getLogger(__name__)


class Region:
    def __init__(
        self,
        locale: dict,
        network_type: str = "walk",
        speed: float = 3.0,
        pbf_path: str | Path | None = None,
        enable_db: bool = False,
        threshold_minutes: float = 15.0,
        cache_dir: str | Path = "data/cache",
        boundary_path: str | Path | None = None,
    ):
        if "city" not in locale:
            raise ValueError("locale must contain a city")

        if pbf_path is None:
            self.settings = None
            self.pbf_path = None
        else:
            self.settings = AnalysisSettings(
                pbf_path=Path(pbf_path),
                cache_dir=Path(cache_dir),
                boundary_path=Path(boundary_path) if boundary_path else None,
                network_type=network_type,
                speed_kmh=speed,
                threshold_minutes=threshold_minutes,
            )
            self.pbf_path = self.settings.pbf_path

        self.locale = locale
        self.network_type = network_type
        self.speed = speed
        self.__graph = None
        self.__services = {}
        self.enable_db = enable_db
        self.threshold_minutes = threshold_minutes
        self.pipeline = AlgorithmPipeline() if enable_db else None
        self.execution_id = None
        self._start_time = None
        self._graph_artifact: OSMGraphArtifact | None = None
        self._node_id_map: dict[int, int] = {}
        self._service_categories = dict(SERVICE_CATEGORIES)
        self._boundary_source: str | None = None
        self._boundary: gpd.GeoDataFrame | None = None

    def build_graph(self) -> nx.MultiDiGraph:
        self._start_time = time.time()
        if self.settings is None:
            raise ValueError("pbf_path is required to build the walking graph")

        boundary = None
        if self.settings.boundary_path is not None:
            boundary = gpd.read_file(self.settings.boundary_path)
            if boundary.empty or boundary.crs is None:
                raise ValueError("boundary file must be non-empty and define a CRS")
            self._boundary_source = str(self.settings.boundary_path)
        elif self.pipeline:
            boundary = self.pipeline.get_city_boundary(
                self.locale["city"],
                self.locale.get("country", "Brazil"),
            )
            if boundary is not None:
                self._boundary_source = "database"
        if boundary is None:
            boundary = ox.geocode_to_gdf(self.locale)
            self._boundary_source = "geocoder"
        self._boundary = boundary

        if self.pipeline:
            self.pipeline.save_city(
                self.locale["city"],
                self.locale.get("country", "Brazil"),
                boundary,
            )
            context = self.pipeline.prepare_execution(
                city_name=self.locale["city"],
                country=self.locale.get("country", "Brazil"),
                speed_kmh=self.speed,
            )
            self.execution_id = context.execution_id

        try:
            artifact = load_or_build_osm_graph(
                self.settings.pbf_path,
                boundary,
                self.settings.cache_dir,
                network_type=self.network_type,
            )
            graph = artifact.graph
            for _origin, _destination, _key, edge_data in graph.edges(
                keys=True, data=True
            ):
                edge_data["speed_kph"] = self.speed
            graph = ox.add_edge_travel_times(graph)
            self.__graph = graph
            self._graph_artifact = artifact

            if self.pipeline and self.execution_id:
                self._node_id_map = self.pipeline.save_graph_nodes(
                    self.execution_id, graph
                )
        except Exception as error:
            if self.pipeline and self.execution_id:
                self.pipeline.fail_execution(self.execution_id, str(error))
            raise

        logger.info(
            "Graph for %s loaded (%s)",
            self.locale["city"],
            "cache" if artifact.cache_hit else "new build",
        )
        return self.__graph

    def locate_services(
        self,
        categories: list[str] | None = None,
        categories_config: dict[str, list[tuple[str, str]]] | None = None,
    ) -> dict[str, list[int]]:
        available_categories = categories_config or SERVICE_CATEGORIES
        selected_categories = categories or list(available_categories)

        unsupported_categories = set(selected_categories) - set(available_categories)
        if unsupported_categories:
            unsupported = ", ".join(sorted(unsupported_categories))
            raise ServiceNotSupportedError(
                f"Unsupported service categories: {unsupported}"
            )

        selected_config = {
            category: available_categories[category] for category in selected_categories
        }
        self._service_categories = selected_config

        if self.__graph is None or self._graph_artifact is None:
            raise RuntimeError("build_graph() must be called before locating services")

        loaded_services = load_services_from_pbf(
            self.__graph,
            self._graph_artifact.region_pbf_path,
            selected_config,
        )
        self.__services = loaded_services.nodes_by_category
        logger.info("Services extracted from the municipal PBF")
        if self.pipeline and self.execution_id:
            self.pipeline.save_services_from_organizer(
                self.execution_id,
                loaded_services.organizer_data(),
                osm_to_db_node_map=self._node_id_map,
            )
        return self.__services

    def calculate_times(self, algorithm: str) -> list:
        runtime_seconds = (
            round(time.time() - self._start_time, 2) if self._start_time else None
        )
        if algorithm == "dijkstra":
            result = multi_source_algorithm(
                G=self.__graph,
                points=self.__services,
                execution_id=self.execution_id,
                pipeline=self.pipeline,
                runtime_seconds=runtime_seconds,
            )
            return result
