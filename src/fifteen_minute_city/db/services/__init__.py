"""
Service/repository layer exposing modular public functions for saving and querying mobility metrics.
"""

from fifteen_minute_city.db.services.city_service import (
    get_city_by_id,
    get_city_by_name_and_country,
    list_cities,
    get_or_create_city,
)
from fifteen_minute_city.db.services.execution_service import (
    create_execution,
    get_execution_by_id,
    list_executions_for_city,
    update_execution_status,
)
from fifteen_minute_city.db.services.category_service import (
    list_categories,
    get_category_by_code,
    seed_default_categories,
)
from fifteen_minute_city.db.services.metrics_service import (
    bulk_save_nodes,
    bulk_save_services,
    bulk_save_node_reachabilities,
    save_city_indices,
    get_city_indices_for_execution,
)

__all__ = [
    "get_city_by_id",
    "get_city_by_name_and_country",
    "list_cities",
    "get_or_create_city",
    "create_execution",
    "get_execution_by_id",
    "list_executions_for_city",
    "update_execution_status",
    "list_categories",
    "get_category_by_code",
    "seed_default_categories",
    "bulk_save_nodes",
    "bulk_save_services",
    "bulk_save_node_reachabilities",
    "save_city_indices",
    "get_city_indices_for_execution",
]
