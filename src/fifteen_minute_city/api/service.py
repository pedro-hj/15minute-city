from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from fifteen_minute_city.db.models.category import ServiceCategory
from fifteen_minute_city.db.models.city import City
from fifteen_minute_city.db.models.execution import Execution
from fifteen_minute_city.db.models.metrics import AccessibilitySummary, CityIndex

PUBLIC_STRATEGIES = {
    "nodes": "network_nodes",
    "population": "population_grid",
}

CATEGORY_METRICS = {
    "total_weight",
    "reachable_weight",
    "within_threshold_weight",
    "unreachable_weight",
    "coverage_percentage",
    "unreachable_percentage",
    "mean_travel_time_minutes",
    "median_travel_time_minutes",
}

OVERALL_METRICS = {
    "total_weight",
    "overall_coverage_percentage",
    "overall_unreachable_percentage",
}


def resolve_strategy(public_strategy: str) -> str | None:
    return PUBLIC_STRATEGIES.get(public_strategy)


def list_public_cities(db: Session) -> list[City]:
    return list(db.scalars(select(City).order_by(City.name, City.country)).all())


def get_city(db: Session, city_id: int) -> City | None:
    return db.get(City, city_id)


def list_public_categories(db: Session) -> list[ServiceCategory]:
    return list(
        db.scalars(select(ServiceCategory).order_by(ServiceCategory.code)).all()
    )


def list_completed_executions(
    db: Session,
    city_id: int,
    *,
    limit: int = 100,
    offset: int = 0,
) -> list[Execution]:
    statement = (
        select(Execution)
        .where(Execution.city_id == city_id, Execution.status == "completed")
        .order_by(Execution.processed_at.desc(), Execution.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement).all())


def latest_completed_execution(db: Session, city_id: int) -> Execution | None:
    statement = (
        select(Execution)
        .where(Execution.city_id == city_id, Execution.status == "completed")
        .order_by(Execution.processed_at.desc(), Execution.id.desc())
        .limit(1)
    )
    return db.scalar(statement)


def get_completed_execution(db: Session, execution_id: int) -> Execution | None:
    return db.scalar(
        select(Execution).where(
            Execution.id == execution_id,
            Execution.status == "completed",
        )
    )


def serialize_execution(execution: Execution) -> dict[str, Any]:
    """Expose execution metadata without leaking input paths or internal errors."""
    return {
        "id": execution.id,
        "city_id": execution.city_id,
        "processed_at": execution.processed_at,
        "status": execution.status,
        "speed_kmh": execution.speed_kmh,
        "threshold_minutes": execution.threshold_minutes,
        "network_type": execution.network_type,
        "execution_time_seconds": execution.execution_time_seconds,
    }


def build_strategy_report(
    db: Session,
    execution_id: int,
    origin_strategy: str,
) -> dict[str, Any] | None:
    summary = db.get(AccessibilitySummary, (execution_id, origin_strategy))
    if summary is None:
        return None

    rows = db.execute(
        select(CityIndex, ServiceCategory)
        .join(ServiceCategory, CityIndex.category_id == ServiceCategory.id)
        .where(
            CityIndex.execution_id == execution_id,
            CityIndex.origin_strategy == origin_strategy,
        )
        .order_by(ServiceCategory.code)
    ).all()
    categories = {
        category.code: {
            "category": category.code,
            "total_weight": index.total_weight,
            "reachable_weight": index.reachable_weight,
            "within_threshold_weight": index.within_threshold_weight,
            "unreachable_weight": index.unreachable_weight,
            "coverage_percentage": index.percentage_within_threshold,
            "unreachable_percentage": index.unreachable_percentage,
            "mean_travel_time_minutes": index.mean_travel_time_minutes,
            "median_travel_time_minutes": index.median_travel_time_minutes,
        }
        for index, category in rows
    }
    return {
        "origin_strategy": origin_strategy,
        "weight_unit": summary.weight_unit,
        "threshold_minutes": summary.threshold_minutes,
        "total_weight": summary.total_weight,
        "categories": categories,
        "overall_coverage_percentage": summary.overall_coverage_percentage,
        "overall_unreachable_percentage": summary.overall_unreachable_percentage,
        "metadata": {},
    }


def build_comparison(
    population_report: dict[str, Any] | None,
    node_report: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if population_report is None or node_report is None:
        return None

    population_categories = population_report["categories"]
    node_categories = node_report["categories"]
    common_categories = sorted(set(population_categories) & set(node_categories))
    return {
        "calculation": "population_report - node_report",
        "unit": "percentage_points",
        "category_coverage_delta": {
            code: round(
                population_categories[code]["coverage_percentage"]
                - node_categories[code]["coverage_percentage"],
                6,
            )
            for code in common_categories
        },
        "category_unreachable_delta": {
            code: round(
                population_categories[code]["unreachable_percentage"]
                - node_categories[code]["unreachable_percentage"],
                6,
            )
            for code in common_categories
        },
        "overall_coverage_delta": round(
            population_report["overall_coverage_percentage"]
            - node_report["overall_coverage_percentage"],
            6,
        ),
        "overall_unreachable_delta": round(
            population_report["overall_unreachable_percentage"]
            - node_report["overall_unreachable_percentage"],
            6,
        ),
    }


def build_detailed_result(db: Session, execution: Execution) -> dict[str, Any]:
    node_report = build_strategy_report(db, execution.id, "graph_nodes")
    population_report = build_strategy_report(db, execution.id, "population_grid")
    return {
        "execution": serialize_execution(execution),
        "node_report": node_report,
        "population_report": population_report,
        "comparison": build_comparison(population_report, node_report),
    }


def extract_metric(
    report: dict[str, Any],
    metric: str,
    *,
    category: str | None = None,
) -> float | None:
    if category is None:
        if metric not in OVERALL_METRICS:
            raise KeyError(metric)
        return report[metric]
    if metric not in CATEGORY_METRICS:
        raise KeyError(metric)
    category_data = report["categories"].get(category)
    if category_data is None:
        raise LookupError(category)
    return category_data[metric]


def metric_unit(report: dict[str, Any], metric: str) -> str:
    if "percentage" in metric:
        return "percent"
    if "time" in metric:
        return "minutes"
    return report["weight_unit"]


def build_metric_response(
    execution: Execution,
    public_strategy: str,
    report: dict[str, Any],
    metric: str,
    *,
    category: str | None = None,
) -> dict[str, Any]:
    return {
        "city_id": execution.city_id,
        "execution_id": execution.id,
        "processed_at": execution.processed_at,
        "strategy": public_strategy,
        "category": category,
        "metric": metric,
        "value": extract_metric(report, metric, category=category),
        "unit": metric_unit(report, metric),
        "threshold_minutes": report["threshold_minutes"],
    }
