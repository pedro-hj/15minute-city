from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from fifteen_minute_city.db.connection import get_db
from fifteen_minute_city.db.services.city_service import get_or_create_city
from fifteen_minute_city.db.services.category_service import seed_default_categories
from fifteen_minute_city.db.services.execution_service import (
    create_execution,
    update_execution_status,
)
from fifteen_minute_city.db.services.metrics_service import (
    bulk_save_nodes,
    bulk_save_services,
    bulk_save_node_reachabilities,
    save_city_indices,
)


@dataclass
class CategoryConfig:
    id: int
    code: str
    display_name: str
    moreno_pillar: str
    osm_tags: List[Dict[str, str]]


@dataclass
class ExecutionContext:
    execution_id: int
    city_id: int
    city_name: str
    country: str
    speed_kmh: float
    categories: List[CategoryConfig]


class AlgorithmPipeline:
    """
    High-level facade orchestrating database workflows for the reachability algorithm developer.
    
    Provides a simple 3-method interface: prepare_execution(), save_execution_results(), and fail_execution().
    """

    def prepare_execution(
        self,
        city_name: str,
        country: str,
        speed_kmh: float = 3.0,
        geom_boundary_geojson: Optional[dict] = None,
    ) -> ExecutionContext:
        """
        Prepare an execution run: ensures city exists, seeds categories, and creates an execution record.

        :param city_name: Name of the city (e.g., 'Praia Grande').
        :param country: Name of the country (e.g., 'Brazil').
        :param speed_kmh: Walking speed in km/h.
        :param geom_boundary_geojson: Optional GeoJSON boundary polygon of the city.
        :return: ExecutionContext containing execution_id and category configuration for OSMnx queries.
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

    def save_execution_results(
        self,
        execution_id: int,
        nodes_data: List[Dict[str, Any]],
        services_data: List[Dict[str, Any]],
        reachabilities_data: List[Dict[str, Any]],
        city_indices_data: List[Dict[str, Any]],
        processing_time_seconds: float,
    ) -> None:
        """
        Bulk save all computation results (nodes, services, reachabilities, city indices) and mark execution as completed.

        :param execution_id: ID of the execution returned by prepare_execution().
        :param nodes_data: List of dicts with 'osm_id', 'lat', 'lon', optional 'overall_index', 'overall_mean_time'.
        :param services_data: List of dicts with 'category_id', 'name', 'lat', 'lon', optional 'osm_node_id'.
        :param reachabilities_data: List of dicts with 'osm_node_id', 'category_id', 'travel_time_minutes', 'within_threshold', optional 'service_index'.
        :param city_indices_data: List of dicts with 'category_id', 'mean_travel_time_minutes', 'percentage_within_threshold', 'overall_index'.
        :param processing_time_seconds: Runtime processing duration in seconds.
        """
        with next(get_db()) as db:
            # 1. Bulk save nodes and get mapping from osm_id -> db_node_id
            node_id_map = bulk_save_nodes(db, execution_id, nodes_data)

            # 2. Resolve representative_node_id for services if osm_node_id provided
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

            # 3. Resolve node_id and closest_service_id for reachabilities
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

            # 4. Save aggregated city indices
            save_city_indices(db, execution_id, city_indices_data)

            # 5. Mark execution status as completed
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

        :param execution_id: Execution ID.
        :param error_message: Exception or failure explanation message.
        """
        with next(get_db()) as db:
            update_execution_status(db, execution_id=execution_id, status="error")
            db.commit()
