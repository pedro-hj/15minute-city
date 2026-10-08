from __future__ import annotations

import logging
import time
from pathlib import Path

import geopandas as gpd
import networkx as nx
import osmnx as ox

from fifteen_minute_city.application.analysis_runner import (
    AccessibilityAnalysisRunner,
    AnalysisOutcome,
)
from fifteen_minute_city.config import AnalysisSettings
from fifteen_minute_city.constants import ANALYSIS_VERSION, SERVICE_CATEGORIES
from fifteen_minute_city.core.modules.exceptions import ServiceNotSupportedError
from fifteen_minute_city.db.pipelines.algorithm_pipeline import AlgorithmPipeline
from fifteen_minute_city.domain.models import OriginSet
from fifteen_minute_city.infrastructure.origins import load_population_grid
from fifteen_minute_city.infrastructure.osm.graph import (
    OSMGraphArtifact,
    load_or_build_osm_graph,
)
from fifteen_minute_city.infrastructure.osm.services import load_services_from_pbf
from fifteen_minute_city.infrastructure.population_catalog import (
    select_population_grids,
)

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
        ibge_code: str | None = None,
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
        self.ibge_code = ibge_code
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
        self._population_origins: OriginSet | None = None

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
                ibge_code=self.ibge_code,
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
                ibge_code=self.ibge_code,
                state=self.locale.get("state"),
            )
            context = self.pipeline.prepare_execution(
                city_name=self.locale["city"],
                country=self.locale.get("country", "Brazil"),
                speed_kmh=self.speed,
                threshold_minutes=self.threshold_minutes,
                network_type=self.network_type,
                pbf_source=str(self.settings.pbf_path),
                ibge_code=self.ibge_code,
                state=self.locale.get("state"),
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
                self.pipeline.update_execution_metadata(
                    self.execution_id,
                    pbf_checksum=artifact.pbf_checksum,
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

    def set_population_origins(self, origins: OriginSet) -> None:
        if origins.weight_unit != "population":
            raise ValueError("population origins must use 'population' as weight_unit")
        self._population_origins = origins

    def load_population_grid(
        self,
        path: str | list[str] | None,
        *,
        population_column: str = "population",
        id_column: str | None = None,
    ) -> OriginSet:
        if self.__graph is None:
            raise RuntimeError("build_graph() must be called before loading origins")
        if self._boundary is None:
            raise RuntimeError("municipality boundary is unavailable")
        logger.info("Clipping the population grid to the municipality boundary")
        if path is None:
            if self.settings is None:
                raise ValueError(
                    "analysis settings required for automatic grid selection"
                )
            selected = select_population_grids(
                self._boundary,
                input_dir=self.settings.pbf_path.parent,
                cache_dir=self.settings.cache_dir,
            )
            path = [str(item) for item in selected]
        origins = load_population_grid(
            path,
            self.__graph,
            population_column=population_column,
            id_column=id_column,
            boundary=self._boundary,
        )
        self.set_population_origins(origins)
        logger.info(
            "Population grid loaded: %d populated cells, total weight %.0f",
            len(origins.origins),
            origins.total_weight,
        )
        if self.pipeline and self.execution_id:
            self.pipeline.update_execution_metadata(
                self.execution_id,
                population_source=origins.source,
                population_column=population_column,
            )
        return origins

    def calculate_accessibility(
        self,
        *,
        include_details: bool = False,
    ) -> AnalysisOutcome:
        if self.__graph is None:
            raise RuntimeError(
                "build_graph() must be called before calculating metrics"
            )
        if not self.__services:
            raise RuntimeError(
                "locate_services() must be called before calculating metrics"
            )

        runner = AccessibilityAnalysisRunner(threshold_minutes=self.threshold_minutes)
        outcome = runner.run(
            self.__graph,
            self.__services,
            population_origins=self._population_origins,
            include_details=include_details or self.pipeline is not None,
            metadata={
                "analysis_version": ANALYSIS_VERSION,
                "locale": self.locale,
                "network_type": self.network_type,
                "speed_kmh": self.speed,
                "threshold_minutes": self.threshold_minutes,
                "categories": list(self._service_categories),
                "services": list(
                    dict.fromkeys(
                        osm_value
                        for filters in self._service_categories.values()
                        for _osm_key, osm_value in filters
                    )
                ),
                "boundary_source": self._boundary_source,
                "pbf_source": str(self.settings.pbf_path) if self.settings else None,
                "pbf_checksum": (
                    self._graph_artifact.pbf_checksum if self._graph_artifact else None
                ),
                "population_source": (
                    self._population_origins.source
                    if self._population_origins
                    else None
                ),
                "graph_cache_key": (
                    self._graph_artifact.cache_key if self._graph_artifact else None
                ),
            },
        )

        if (
            self.pipeline
            and self.execution_id
            and hasattr(self.pipeline, "save_accessibility_outcome")
        ):
            runtime_seconds = (
                round(time.time() - self._start_time, 2) if self._start_time else None
            )
            try:
                self.pipeline.save_accessibility_outcome(
                    execution_id=self.execution_id,
                    outcome=outcome,
                    graph_node_to_db_id=self._node_id_map,
                    processing_time_seconds=runtime_seconds,
                )
            except Exception as error:
                logger.exception("Failed to persist accessibility results")
                self.pipeline.fail_execution(self.execution_id, str(error))
                raise

        return outcome

    def calculate_times(self, algorithm: str = "dijkstra") -> dict:
        if algorithm != "dijkstra":
            raise ValueError(f"Unsupported shortest-path algorithm: {algorithm}")
        return self.calculate_accessibility().primary_report.to_dict()
