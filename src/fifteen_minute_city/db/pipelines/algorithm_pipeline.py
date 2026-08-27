from dataclasses import dataclass
from typing import Any

import geopandas as gpd
import networkx as nx

from fifteen_minute_city.db.connection import get_db
from fifteen_minute_city.db.models.city import City
from fifteen_minute_city.db.models.metrics import CityIndex
from fifteen_minute_city.db.models.service import Service
from fifteen_minute_city.db.services.category_service import (
    list_categories,
    seed_default_categories,
)
from fifteen_minute_city.db.services.city_service import (
    get_city_boundary_gdf,
    get_or_create_city,
    save_city_boundary_from_gdf,
)
from fifteen_minute_city.db.services.execution_service import (
    create_execution,
    update_execution_status,
)
from fifteen_minute_city.db.services.metrics_service import (
    bulk_save_node_reachabilities,
    bulk_save_nodes,
    bulk_save_services,
    get_services_by_execution,
    save_city_indices,
    save_city_indices_from_metrics,
    save_graph_nodes_from_nx,
    save_services_from_organizer_dict,
)


@dataclass
class CategoryConfig:
    id: int
    code: str
    display_name: str
    moreno_pillar: str
    osm_tags: list[dict[str, str]]


@dataclass
class ExecutionContext:
    execution_id: int
    city_id: int
    city_name: str
    country: str
    speed_kmh: float
    categories: list[CategoryConfig]

    @property
    def category_id_map(self) -> dict[str, int]:
        """Mapping from category code (e.g. 'bank') -> category database ID."""
        return {cat.code: cat.id for cat in self.categories}


class AlgorithmPipeline:
    """
    High-level facade orchestrating database workflows for the reachability algorithm developer.
    
    Provides simple methods for each RECOVERY and PERSISTENCE point:
    - get_city_boundary() [RP 1]
    - save_city() [PP 1]
    - prepare_execution()
    - save_graph_nodes() [PP 2]
    - get_execution_services() [RP 2]
    - save_services_from_organizer() [PP 3]
    - save_algorithm_metrics() [PP 4]
    """

    def get_city_boundary(
        self, city_name: str, country: str = "Brazil"
    ) -> gpd.GeoDataFrame | None:
        """
        [RECOVERY POINT 1]
        Retrieve the geographic boundary GeoDataFrame from the database if already stored.
        """
        with next(get_db()) as db:
            return get_city_boundary_gdf(db, name=city_name, country=country)

    def save_city(
        self, city_name: str, country: str, boundary_gdf: gpd.GeoDataFrame
    ) -> City:
        """
        [PERSISTENCE POINT 1]
        Save or update the city boundary polygon in the 'city' table.
        """
        with next(get_db()) as db:
            return save_city_boundary_from_gdf(
                db, name=city_name, country=country, gdf=boundary_gdf
            )

    def prepare_execution(
        self,
        city_name: str,
        country: str,
        speed_kmh: float = 3.0,
        geom_boundary_geojson: dict | None = None,
    ) -> ExecutionContext:
        """
        Prepare an execution run: ensures city exists, seeds categories, and creates an execution record.

        :param city_name: Name of the city (e.g., 'Praia Grande').
        :param country: Name of the country (e.g., 'Brazil').
        :param speed_kmh: Walking speed in km/h.
        :param geom_boundary_geojson: Optional GeoJSON boundary polygon of the city.
        :return: ExecutionContext containing execution_id and category configuration.
        """
        with next(get_db()) as db:
            # 1. Get or create target city
            city = get_or_create_city(
                db, name=city_name, country=country, geom_boundary_geojson=geom_boundary_geojson
            )

            # 2. Ensure standard 15-minute city categories are seeded
            categories = seed_default_categories(db)

            # 3. Create execution record in 'processing' status
            execution = create_execution(db, city_id=city.id, speed_kmh=speed_kmh, status="processing")

            # 4. Map category configurations for algorithm developer
            category_configs = [
                CategoryConfig(
                    id=cat.id,
                    code=cat.code,
                    display_name=cat.display_name,
                    moreno_pillar=cat.moreno_pillar,
                    osm_tags=[{"key": tag.osm_key, "value": tag.osm_value} for tag in cat.osm_tags],
                )
                for cat in categories
            ]

            return ExecutionContext(
                execution_id=execution.id,
                city_id=city.id,
                city_name=city.name,
                country=city.country,
                speed_kmh=execution.speed_kmh,
                categories=category_configs,
            )

    def save_graph_nodes(
        self, execution_id: int, G: nx.MultiDiGraph
    ) -> dict[int, int]:
        """
        [PERSISTENCE POINT 2]
        Extract all nodes from NetworkX graph and bulk save them into the 'node' table.

        :param execution_id: Target execution run ID.
        :param G: NetworkX graph with 'x' (lon) and 'y' (lat) attributes.
        :return: Mapping from osm_id -> db node.id.
        """
        with next(get_db()) as db:
            node_map = save_graph_nodes_from_nx(db, execution_id, G)
            db.commit()
            return node_map

    def get_execution_services(self, execution_id: int) -> list[Service]:
        """
        [RECOVERY POINT 2]
        Retrieve physical services stored for a given execution run.
        """
        with next(get_db()) as db:
            return get_services_by_execution(db, execution_id)

    def save_services_from_organizer(
        self,
        execution_id: int,
        organized_data: dict[str, list[list[Any]]],
        osm_to_db_node_map: dict[int, int] | None = None,
    ) -> list[Service]:
        """
        [PERSISTENCE POINT 3]
        Save organized service establishments into the 'service' table.

        :param execution_id: Target execution run ID.
        :param organized_data: Output dictionary from organizes_data().
        :param osm_to_db_node_map: Optional mapping from osm_id -> db node.id.
        :return: List of saved Service models.
        """
        with next(get_db()) as db:
            categories = list_categories(db)
            category_id_map = {cat.code: cat.id for cat in categories}
            saved_services = save_services_from_organizer_dict(
                db,
                execution_id=execution_id,
                organized_data=organized_data,
                category_id_map=category_id_map,
                osm_to_db_node_map=osm_to_db_node_map,
            )
            db.commit()
            return saved_services

    def save_algorithm_metrics(
        self,
        execution_id: int,
        metrics_list: list[dict[str, Any]],
        processing_time_seconds: float | None = None,
    ) -> list[CityIndex]:
        """
        [PERSISTENCE POINT 4]
        Save aggregated city metrics (mean, median, etc.) into the 'city_index' table
        and mark the execution run as completed.

        :param execution_id: Target execution run ID.
        :param metrics_list: Output from multi_source_algorithm().
        :param processing_time_seconds: Total algorithm runtime in seconds.
        :return: List of saved CityIndex models.
        """
        with next(get_db()) as db:
            categories = list_categories(db)
            category_id_map = {cat.code: cat.id for cat in categories}
            saved_indices = save_city_indices_from_metrics(
                db,
                execution_id=execution_id,
                metrics_list=metrics_list,
                category_id_map=category_id_map,
            )
            update_execution_status(
                db,
                execution_id=execution_id,
                status="completed",
                execution_time_seconds=processing_time_seconds,
            )
            db.commit()
            return saved_indices

    def save_execution_results(
        self,
        execution_id: int,
        nodes_data: list[dict[str, Any]],
        services_data: list[dict[str, Any]],
        reachabilities_data: list[dict[str, Any]],
        city_indices_data: list[dict[str, Any]],
        processing_time_seconds: float,
    ) -> None:
        """
        Bulk save all computation results and mark execution as completed.
        """
        with next(get_db()) as db:
            node_id_map = bulk_save_nodes(db, execution_id, nodes_data)

            prepared_services = []
            for s in services_data:
                rep_node_id = s.get("representative_node_id")
                if not rep_node_id and "osm_node_id" in s:
                    rep_node_id = node_id_map.get(s["osm_node_id"])

                prepared_services.append(
                    {
                        "category_id": s["category_id"],
                        "name": s.get("name"),
                        "lat": s["lat"],
                        "lon": s["lon"],
                        "representative_node_id": rep_node_id,
                    }
                )

            saved_services = bulk_save_services(db, execution_id, prepared_services)

            prepared_reachabilities = []
            for r in reachabilities_data:
                node_id = r.get("node_id")
                if not node_id and "osm_node_id" in r:
                    node_id = node_id_map.get(r["osm_node_id"])

                service_id = r.get("closest_service_id")
                if not service_id and "service_index" in r and r["service_index"] is not None:
                    service_id = saved_services[r["service_index"]].id

                if node_id:
                    prepared_reachabilities.append(
                        {
                            "node_id": node_id,
                            "category_id": r["category_id"],
                            "closest_service_id": service_id,
                            "travel_time_minutes": r["travel_time_minutes"],
                            "within_threshold": r["within_threshold"],
                        }
                    )

            bulk_save_node_reachabilities(db, prepared_reachabilities)
            save_city_indices(db, execution_id, city_indices_data)

            update_execution_status(
                db,
                execution_id=execution_id,
                status="completed",
                execution_time_seconds=processing_time_seconds,
            )
            db.commit()

    def fail_execution(self, execution_id: int, error_message: str) -> None:
        """
        Mark an execution as failed with status 'error'.
        """
        with next(get_db()) as db:
            update_execution_status(db, execution_id=execution_id, status="error")
            db.commit()
