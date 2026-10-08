from collections.abc import Iterator
from typing import Any

import networkx as nx
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from fifteen_minute_city.db.models.metrics import (
    AccessibilitySummary,
    CityIndex,
    NodeReachability,
)
from fifteen_minute_city.db.models.node import Node
from fifteen_minute_city.db.models.service import Service
from fifteen_minute_city.domain.models import AccessibilityReport


def _chunks[T](items: list[T], size: int = 5_000) -> Iterator[list[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def bulk_save_nodes(
    db: Session,
    execution_id: int,
    nodes_data: list[dict[str, Any]],
) -> dict[int, int]:
    """
    Bulk insert network nodes for an execution run.

    :param db: SQLAlchemy Session.
    :param execution_id: Execution run ID.
    :param nodes_data: List of dicts containing keys: 'osm_id', 'lat', 'lon', optional 'overall_index', 'overall_mean_time'.
    :return: Dictionary mapping osm_id -> database node primary key ID.
    """
    records = []
    for data in nodes_data:
        geom = from_shape(Point(data["lon"], data["lat"]), srid=4326)
        records.append(
            {
                "execution_id": execution_id,
                "osm_id": data["osm_id"],
                "geom": geom,
                "overall_index": data.get("overall_index"),
                "overall_mean_time": data.get("overall_mean_time"),
            }
        )

    node_map = {}
    for batch in _chunks(records):
        rows = db.execute(
            insert(Node).returning(Node.id, Node.osm_id),
            batch,
        ).all()
        node_map.update({int(row.osm_id): int(row.id) for row in rows})
    return node_map


def save_graph_nodes_from_nx(
    db: Session,
    execution_id: int,
    G: nx.MultiDiGraph,
) -> dict[int, int]:
    """
    Extract nodes from a NetworkX MultiDiGraph and bulk save them for the execution.

    :param db: SQLAlchemy Session.
    :param execution_id: Execution run ID.
    :param G: NetworkX MultiDiGraph with 'x' (lon) and 'y' (lat) node attributes.
    :return: Dictionary mapping osm_id -> database node primary key ID.
    """
    nodes_data = []
    for node_id, data in G.nodes(data=True):
        lon = data.get("x")
        lat = data.get("y")
        if lon is not None and lat is not None:
            nodes_data.append(
                {
                    "osm_id": int(node_id),
                    "lon": float(lon),
                    "lat": float(lat),
                }
            )

    return bulk_save_nodes(db, execution_id, nodes_data)


def bulk_save_services(
    db: Session,
    execution_id: int,
    services_data: list[dict[str, Any]],
) -> list[Service]:
    """
    Bulk insert physical service establishments for an execution run.

    :param db: SQLAlchemy Session.
    :param execution_id: Execution run ID.
    :param services_data: List of dicts containing: 'category_id', 'name', 'lat', 'lon', optional 'representative_node_id'.
    :return: List of created Service model instances.
    """
    records = []
    for data in services_data:
        geom = from_shape(Point(data["lon"], data["lat"]), srid=4326)
        records.append(
            {
                "execution_id": execution_id,
                "category_id": data["category_id"],
                "representative_node_id": data.get("representative_node_id"),
                "name": data.get("name"),
                "geom": geom,
            }
        )

    saved_services = []
    for batch in _chunks(records):
        saved_services.extend(
            db.scalars(insert(Service).returning(Service), batch).all()
        )
    return saved_services


def save_services_from_organizer_dict(
    db: Session,
    execution_id: int,
    organized_data: dict[str, list[list[Any]]],
    category_id_map: dict[str, int],
    osm_to_db_node_map: dict[int, int] | None = None,
) -> list[Service]:
    """
    Save services from the organizer structure:
    {
        'category_code': [
            ['Service Name', OSM_NODE_ID, ShapelyPoint],
            ...
        ]
    }

    :param db: SQLAlchemy Session.
    :param execution_id: Execution run ID.
    :param organized_data: Dictionary structured from organizes_data().
    :param category_id_map: Mapping from category_code (e.g. 'health') -> category_id.
    :param osm_to_db_node_map: Optional mapping from osm_id -> db node.id.
    :return: List of created Service model instances.
    """
    services_data = []
    for category_code, items in organized_data.items():
        cat_id = category_id_map.get(category_code)
        if not cat_id:
            continue

        for item in items:
            name = item[0] if len(item) > 0 and item[0] else category_code
            osm_node_id = item[1] if len(item) > 1 else None
            point_geom = item[2] if len(item) > 2 else None

            rep_node_id = None
            if osm_node_id is not None and osm_to_db_node_map:
                rep_node_id = osm_to_db_node_map.get(int(osm_node_id))

            if (
                point_geom is not None
                and hasattr(point_geom, "x")
                and hasattr(point_geom, "y")
            ):
                services_data.append(
                    {
                        "category_id": cat_id,
                        "name": str(name),
                        "lat": float(point_geom.y),
                        "lon": float(point_geom.x),
                        "representative_node_id": rep_node_id,
                    }
                )

    if services_data:
        return bulk_save_services(db, execution_id, services_data)
    return []


def get_services_by_execution(db: Session, execution_id: int) -> list[Service]:
    """Retrieve all physical services associated with a specific execution."""
    return list(
        db.scalars(select(Service).where(Service.execution_id == execution_id)).all()
    )


def bulk_save_node_reachabilities(
    db: Session,
    reachabilities_data: list[dict[str, Any]],
) -> None:
    """
    Bulk insert travel reachability records for nodes.

    :param db: SQLAlchemy Session.
    :param reachabilities_data: List of dicts containing: 'node_id', 'category_id', 'travel_time_minutes', 'within_threshold', optional 'closest_service_id'.
    """
    records = [
        {
            "node_id": data["node_id"],
            "category_id": data["category_id"],
            "closest_service_id": data.get("closest_service_id"),
            "travel_time_minutes": data["travel_time_minutes"],
            "reachable": data.get("reachable", True),
            "within_threshold": data["within_threshold"],
        }
        for data in reachabilities_data
    ]
    for batch in _chunks(records):
        db.execute(insert(NodeReachability), batch)


def get_city_indices_for_execution(db: Session, execution_id: int) -> list[CityIndex]:
    """Retrieve aggregated city index metrics for a specific execution."""
    return list(
        db.scalars(
            select(CityIndex).where(CityIndex.execution_id == execution_id)
        ).all()
    )


def save_accessibility_report(
    db: Session,
    execution_id: int,
    report: AccessibilityReport,
    category_id_map: dict[str, int],
) -> tuple[list[CityIndex], AccessibilitySummary]:
    """Persist category and overall indicators from the domain report."""
    indices = []
    for category_code, metrics in report.categories.items():
        category_id = category_id_map.get(category_code)
        if category_id is None:
            raise ValueError(
                f"Service category '{category_code}' is not registered in the database"
            )

        index = CityIndex(
            execution_id=execution_id,
            category_id=category_id,
            origin_strategy=report.origin_strategy,
            weight_unit=report.weight_unit,
            threshold_minutes=report.threshold_minutes,
            total_weight=metrics.total_weight,
            reachable_weight=metrics.reachable_weight,
            within_threshold_weight=metrics.within_threshold_weight,
            unreachable_weight=metrics.unreachable_weight,
            mean_travel_time_minutes=metrics.mean_travel_time_minutes,
            median_travel_time_minutes=metrics.median_travel_time_minutes,
            percentage_within_threshold=metrics.coverage_percentage,
            unreachable_percentage=metrics.unreachable_percentage,
            overall_index=metrics.coverage_percentage,
        )
        indices.append(db.merge(index))

    summary = AccessibilitySummary(
        execution_id=execution_id,
        origin_strategy=report.origin_strategy,
        weight_unit=report.weight_unit,
        threshold_minutes=report.threshold_minutes,
        total_weight=report.total_weight,
        overall_coverage_percentage=report.overall_coverage_percentage,
        overall_unreachable_percentage=report.overall_unreachable_percentage,
        overall_score=report.overall_coverage_percentage,
    )
    summary = db.merge(summary)
    db.flush()
    return indices, summary
