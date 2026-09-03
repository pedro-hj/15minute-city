"""
Service/repository layer exposing modular public functions for saving and querying mobility metrics.
"""

from fifteen_minute_city.db.services.category_service import (
    get_category_by_code,
    list_categories,
    seed_default_categories,
)
from fifteen_minute_city.db.services.city_service import (
    get_city_boundary_gdf,
    get_city_by_id,
    get_city_by_name_and_country,
    get_or_create_city,
    list_cities,
    save_city_boundary_from_gdf,
)
from fifteen_minute_city.db.services.execution_service import (
    create_execution,
    get_execution_by_id,
    list_executions_for_city,
    update_execution_status,
)
from fifteen_minute_city.db.services.metrics_service import (
    bulk_save_node_reachabilities,
    bulk_save_nodes,
    bulk_save_services,
    get_city_indices_for_execution,
    get_services_by_execution,
    save_city_indices,
    save_city_indices_from_metrics,
    save_graph_nodes_from_nx,
    save_services_from_organizer_dict,
)

__all__ = [
    "bulk_save_node_reachabilities",
    "bulk_save_nodes",
    "bulk_save_services",
    "create_execution",
    "get_category_by_code",
    "get_city_boundary_gdf",
    "get_city_by_id",
    "get_city_by_name_and_country",
    "get_city_indices_for_execution",
    "get_execution_by_id",
    "get_or_create_city",
    "get_services_by_execution",
    "list_categories",
    "list_cities",
    "list_executions_for_city",
    "save_city_boundary_from_gdf",
    "save_city_indices",
    "save_city_indices_from_metrics",
    "save_graph_nodes_from_nx",
    "save_services_from_organizer_dict",
    "seed_default_categories",
    "update_execution_status",
]
