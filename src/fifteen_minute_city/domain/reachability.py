from __future__ import annotations

from collections.abc import Collection, Mapping
from math import isfinite

import networkx as nx

from fifteen_minute_city.domain.models import (
    AccessibilityComparison,
    AccessibilityReport,
    CategoryAccessibility,
    OriginAccessibility,
    OriginSet,
)


def _weighted_median(values_and_weights: list[tuple[float, float]]) -> float | None:
    if not values_and_weights:
        return None

    ordered = sorted(values_and_weights)
    half_weight = sum(weight for _value, weight in ordered) / 2
    cumulative_weight = 0.0
    for value, weight in ordered:
        cumulative_weight += weight
        if cumulative_weight >= half_weight:
            return value
    return ordered[-1][0]


def _validate_graph(graph: nx.Graph, weight: str) -> None:
    if not graph:
        raise ValueError("the walking graph must not be empty")

    for _origin, _destination, edge_data in graph.edges(data=True):
        value = edge_data.get(weight)
        if not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
            raise ValueError(
                f"every graph edge must contain a finite non-negative '{weight}'"
            )


def analyze_accessibility(
    graph: nx.Graph,
    service_nodes_by_category: Mapping[str, Collection[int]],
    origins: OriginSet,
    *,
    threshold_minutes: float = 15.0,
    weight: str = "travel_time",
    include_details: bool = False,
    metadata: Mapping[str, object] | None = None,
) -> AccessibilityReport:
    """Calculate population-weighted accessibility for every service category."""
    if threshold_minutes <= 0 or not isfinite(threshold_minutes):
        raise ValueError("threshold_minutes must be a finite value greater than zero")
    if not service_nodes_by_category:
        raise ValueError("at least one service category is required")

    _validate_graph(graph, weight)
    graph_nodes = set(graph.nodes)
    invalid_origin_nodes = {
        origin.node_id
        for origin in origins.origins
        if origin.node_id not in graph_nodes
    }
    if invalid_origin_nodes:
        raise ValueError(
            f"origin nodes are absent from the graph: {sorted(invalid_origin_nodes)}"
        )

    threshold_seconds = threshold_minutes * 60.0
    total_weight = origins.total_weight
    within_every_category = {origin.origin_id: True for origin in origins.origins}
    unreachable_in_any_category = {
        origin.origin_id: False for origin in origins.origins
    }
    category_results: dict[str, CategoryAccessibility] = {}

    search_graph = graph.reverse(copy=False) if graph.is_directed() else graph

    for category, configured_sources in service_nodes_by_category.items():
        sources = set(configured_sources)
        invalid_sources = sources - graph_nodes
        if invalid_sources:
            raise ValueError(
                f"service nodes for '{category}' are absent from the graph: "
                f"{sorted(invalid_sources)}"
            )

        if sources:
            if include_details:
                distances, paths = nx.multi_source_dijkstra(
                    search_graph,
                    sources=sources,
                    weight=weight,
                )
            else:
                distances = nx.multi_source_dijkstra_path_length(
                    search_graph,
                    sources=sources,
                    weight=weight,
                )
                paths = {}
        else:
            distances, paths = {}, {}

        reachable_weight = 0.0
        within_threshold_weight = 0.0
        weighted_times: list[tuple[float, float]] = []
        details: list[OriginAccessibility] = []

        for origin in origins.origins:
            travel_time_seconds = distances.get(origin.node_id)
            if travel_time_seconds is None:
                travel_time_minutes = None
                nearest_service_node_id = None
                unreachable_in_any_category[origin.origin_id] = True
            else:
                reachable_weight += origin.weight
                travel_time_minutes = travel_time_seconds / 60.0
                weighted_times.append((travel_time_minutes, origin.weight))
                nearest_service_node_id = (
                    int(paths[origin.node_id][0]) if include_details else None
                )

            within_threshold = (
                travel_time_seconds is not None
                and travel_time_seconds <= threshold_seconds
            )
            if within_threshold:
                within_threshold_weight += origin.weight
            else:
                within_every_category[origin.origin_id] = False

            if include_details:
                details.append(
                    OriginAccessibility(
                        origin=origin,
                        travel_time_minutes=travel_time_minutes,
                        nearest_service_node_id=nearest_service_node_id,
                    )
                )

        mean_time = None
        if reachable_weight:
            mean_time = (
                sum(value * item_weight for value, item_weight in weighted_times)
                / reachable_weight
            )

        category_results[category] = CategoryAccessibility(
            category=category,
            threshold_minutes=threshold_minutes,
            total_weight=total_weight,
            reachable_weight=reachable_weight,
            within_threshold_weight=within_threshold_weight,
            mean_travel_time_minutes=mean_time,
            median_travel_time_minutes=_weighted_median(weighted_times),
            details=tuple(details),
        )

    overall_within_weight = sum(
        origin.weight
        for origin in origins.origins
        if within_every_category[origin.origin_id]
    )
    overall_unreachable_weight = sum(
        origin.weight
        for origin in origins.origins
        if unreachable_in_any_category[origin.origin_id]
    )

    return AccessibilityReport(
        origin_strategy=origins.strategy,
        weight_unit=origins.weight_unit,
        threshold_minutes=threshold_minutes,
        total_weight=total_weight,
        categories=category_results,
        overall_within_threshold_weight=overall_within_weight,
        overall_unreachable_weight=overall_unreachable_weight,
        metadata=dict(metadata or {}),
    )


def compare_accessibility(
    population_report: AccessibilityReport,
    node_report: AccessibilityReport,
) -> AccessibilityComparison:
    """Compare population-weighted results with the graph-node baseline."""
    return AccessibilityComparison(population_report, node_report)
