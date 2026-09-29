from __future__ import annotations

import logging
import time
from pathlib import Path

import networkx as nx
import osmnx as ox

from fifteen_minute_city.constants import OSM_SERVICE_TAGS, PATH_OSM_MAPS
from fifteen_minute_city.core.modules.algorithms import multi_source_algorithm
from fifteen_minute_city.core.modules.osm_utils import (
    load_osm_graph,
    load_services_geojson,
)
from fifteen_minute_city.db.pipelines.algorithm_pipeline import AlgorithmPipeline

logger = logging.getLogger(__name__)


class Region:
    def __init__(
        self,
        locale: dict,
        network_type: str,
        speed: float,
        pbf_path: str | Path,
        enable_db: bool = True,
    ):
        self.locale = locale
        self.network_type = network_type
        self.speed = speed
        self.pbf_path = Path(pbf_path).expanduser().resolve()
        self.__graph = None
        self.__services = {}
        self.__path = None
        self.enable_db = enable_db
        self.pipeline = AlgorithmPipeline() if enable_db else None
        self.execution_id = None
        self._start_time = None

    def build_graph(self) -> nx.MultiDiGraph:
        self._start_time = time.time()

        # Initialize execution in database if enabled
        if self.pipeline:
            try:
                ctx = self.pipeline.prepare_execution(
                    city_name=self.locale["city"],
                    country=self.locale.get("country", "Brazil"),
                    speed_kmh=self.speed,
                )
                self.execution_id = ctx.execution_id
            except Exception as e:  # noqa: BLE001
                logger.debug("Database execution initialization skipped: %s", e)
                self.execution_id = None

        hwy_speeds = {
            "motorway": self.speed,
            "trunk": self.speed,
            "primary": self.speed,
            "secondary": self.speed,
            "tertiary": self.speed,
            "residential": self.speed,
            "service": self.speed,
        }

        graph = load_osm_graph(
            pbf_path=self.pbf_path,
            region=self.locale,
            network_type=self.network_type,
            execution_id=self.execution_id,
            pipeline=self.pipeline,
        )
        graph = ox.add_edge_speeds(graph, hwy_speeds=hwy_speeds)
        graph = ox.add_edge_travel_times(graph)

        self.__graph = graph
        self.__path = PATH_OSM_MAPS / self.locale["city"]

        print(
            f"Graph of region \033[1m{self.locale['city']}\033[0m successfully generated."
        )

        return self.__graph

    def locate_services(self, services: list[str] | None = None) -> dict:
        if services is None:
            s_formatted = OSM_SERVICE_TAGS
        else:
            s_formatted = {}
            for name, tag in OSM_SERVICE_TAGS.items():
                intersection = list(set(services) & set(tag))
                if intersection:
                    s_formatted[name] = intersection

        self.__services = load_services_geojson(
            G=self.__graph,
            pbf_region_path=str(self.__path),
            services=s_formatted,
            execution_id=self.execution_id,
            pipeline=self.pipeline,
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
