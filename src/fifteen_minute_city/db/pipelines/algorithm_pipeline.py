from dataclasses import dataclass
from typing import Any

import geopandas as gpd
import networkx as nx

from fifteen_minute_city.application.analysis_runner import AnalysisOutcome
from fifteen_minute_city.db.connection import session_scope
from fifteen_minute_city.db.models.city import City
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
    update_execution_metadata,
    update_execution_status,
)
from fifteen_minute_city.db.services.metrics_service import (
    bulk_save_node_reachabilities,
    get_services_by_execution,
    save_accessibility_report,
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
        """Mapping from category code (e.g. 'health') -> category database ID."""
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
    - save_accessibility_outcome() [PP 4]
    """

    def get_city_boundary(
        self, city_name: str, country: str = "Brazil", ibge_code: str | None = None
    ) -> gpd.GeoDataFrame | None:
        """
        [RECOVERY POINT 1]
        Retrieve the geographic boundary GeoDataFrame from the database if already stored.
        """
        with session_scope() as db:
            return get_city_boundary_gdf(
                db, name=city_name, country=country, ibge_code=ibge_code
            )

    def save_city(
        self,
        city_name: str,
        country: str,
        boundary_gdf: gpd.GeoDataFrame,
        ibge_code: str | None = None,
        state: str | None = None,
    ) -> City:
        """
        [PERSISTENCE POINT 1]
        Save or update the city boundary polygon in the 'city' table.
        """
        with session_scope() as db:
            return save_city_boundary_from_gdf(
                db,
                name=city_name,
                country=country,
                gdf=boundary_gdf,
                ibge_code=ibge_code,
                state=state,
            )

    def prepare_execution(
        self,
        city_name: str,
        country: str,
        speed_kmh: float = 3.0,
        threshold_minutes: float = 15.0,
        network_type: str = "walk",
        pbf_source: str | None = None,
        population_source: str | None = None,
        population_column: str | None = None,
        geom_boundary_geojson: dict | None = None,
        ibge_code: str | None = None,
        state: str | None = None,
    ) -> ExecutionContext:
        """
        Prepare an execution run: ensures city exists, seeds categories, and creates an execution record.

        :param city_name: Name of the city (e.g., 'Praia Grande').
        :param country: Name of the country (e.g., 'Brazil').
        :param speed_kmh: Walking speed in km/h.
        :param geom_boundary_geojson: Optional GeoJSON boundary polygon of the city.
        :return: ExecutionContext containing execution_id and category configuration.
        """
        with session_scope() as db:
            # 1. Get or create target city
            city = get_or_create_city(
                db,
                name=city_name,
                country=country,
                geom_boundary_geojson=geom_boundary_geojson,
                ibge_code=ibge_code,
                state=state,
            )

            # 2. Ensure standard 15-minute city categories are seeded
            categories = seed_default_categories(db)

            # 3. Create execution record in 'processing' status
            execution = create_execution(
                db,
                city_id=city.id,
                speed_kmh=speed_kmh,
                status="processing",
                threshold_minutes=threshold_minutes,
                network_type=network_type,
                pbf_source=pbf_source,
                population_source=population_source,
                population_column=population_column,
            )

            # 4. Map category configurations for algorithm developer
            category_configs = [
                CategoryConfig(
                    id=cat.id,
                    code=cat.code,
                    display_name=cat.display_name,
                    moreno_pillar=cat.moreno_pillar,
                    osm_tags=[
                        {"key": tag.osm_key, "value": tag.osm_value}
                        for tag in cat.osm_tags
                    ],
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

    def save_graph_nodes(self, execution_id: int, G: nx.MultiDiGraph) -> dict[int, int]:
        """
        [PERSISTENCE POINT 2]
        Extract all nodes from NetworkX graph and bulk save them into the 'node' table.

        :param execution_id: Target execution run ID.
        :param G: NetworkX graph with 'x' (lon) and 'y' (lat) attributes.
        :return: Mapping from osm_id -> db node.id.
        """
        with session_scope() as db:
            node_map = save_graph_nodes_from_nx(db, execution_id, G)
            db.commit()
            return node_map

    def get_execution_services(self, execution_id: int) -> list[Service]:
        """
        [RECOVERY POINT 2]
        Retrieve physical services stored for a given execution run.
        """
        with session_scope() as db:
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
        with session_scope() as db:
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

    def fail_execution(self, execution_id: int, error_message: str) -> None:
        """
        Mark an execution as failed with status 'error'.
        """
        with session_scope() as db:
            update_execution_status(
                db,
                execution_id=execution_id,
                status="error",
                error_message=error_message,
            )
            db.commit()

    def save_accessibility_outcome(
        self,
        execution_id: int,
        outcome: AnalysisOutcome,
        graph_node_to_db_id: dict[int, int] | None = None,
        processing_time_seconds: float | None = None,
    ) -> None:
        """Persist both origin strategies and mark the execution as complete."""
        reports = [outcome.node_report]
        if outcome.population_report is not None:
            reports.append(outcome.population_report)

        with session_scope() as db:
            categories = list_categories(db)
            category_id_map = {category.code: category.id for category in categories}
            for report in reports:
                save_accessibility_report(
                    db,
                    execution_id=execution_id,
                    report=report,
                    category_id_map=category_id_map,
                )

            if graph_node_to_db_id:
                services = get_services_by_execution(db, execution_id)
                service_by_category_and_node = {
                    (service.category_id, service.representative_node_id): service.id
                    for service in services
                    if service.representative_node_id is not None
                }
                reachabilities = []
                for category_code, metrics in outcome.node_report.categories.items():
                    category_id = category_id_map[category_code]
                    for detail in metrics.details:
                        database_node_id = graph_node_to_db_id.get(detail.node_id)
                        if database_node_id is None:
                            continue
                        nearest_database_node_id = (
                            graph_node_to_db_id.get(detail.nearest_service_node_id)
                            if detail.nearest_service_node_id is not None
                            else None
                        )
                        reachabilities.append(
                            {
                                "node_id": database_node_id,
                                "category_id": category_id,
                                "closest_service_id": service_by_category_and_node.get(
                                    (category_id, nearest_database_node_id)
                                ),
                                "travel_time_minutes": detail.travel_time_minutes,
                                "reachable": detail.reachable,
                                "within_threshold": detail.is_within(
                                    metrics.threshold_minutes
                                ),
                            }
                        )
                bulk_save_node_reachabilities(db, reachabilities)

            update_execution_metadata(
                db,
                execution_id,
                analysis_metadata=outcome.primary_report.metadata,
            )

            update_execution_status(
                db,
                execution_id=execution_id,
                status="completed",
                execution_time_seconds=processing_time_seconds,
            )
            db.commit()

    def update_execution_metadata(
        self,
        execution_id: int,
        *,
        pbf_checksum: str | None = None,
        population_source: str | None = None,
        population_column: str | None = None,
        analysis_metadata: dict | None = None,
    ) -> None:
        with session_scope() as db:
            update_execution_metadata(
                db,
                execution_id,
                pbf_checksum=pbf_checksum,
                population_source=population_source,
                population_column=population_column,
                analysis_metadata=analysis_metadata,
            )
            db.commit()
