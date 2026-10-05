from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import networkx as nx

from fifteen_minute_city.domain.models import (
    AccessibilityComparison,
    AccessibilityReport,
    OriginSet,
)
from fifteen_minute_city.domain.reachability import (
    analyze_accessibility,
    compare_accessibility,
)
from fifteen_minute_city.infrastructure.origins import origins_from_graph_nodes


@dataclass(frozen=True, slots=True)
class AnalysisOutcome:
    """Reports produced by the population and graph-node approaches."""

    primary_report: AccessibilityReport
    node_report: AccessibilityReport
    population_report: AccessibilityReport | None = None
    comparison: AccessibilityComparison | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_report": self.node_report.to_dict(),
            "population_report": (
                self.population_report.to_dict() if self.population_report else None
            ),
            "comparison": self.comparison.to_dict() if self.comparison else None,
        }


class AccessibilityAnalysisRunner:
    """Coordinate comparable accessibility analyses without persistence concerns."""

    def __init__(self, *, threshold_minutes: float = 15.0) -> None:
        self.threshold_minutes = threshold_minutes

    def run(
        self,
        graph: nx.MultiDiGraph,
        service_nodes_by_category: dict[str, list[int]],
        *,
        population_origins: OriginSet | None = None,
        include_details: bool = False,
        metadata: dict[str, object] | None = None,
    ) -> AnalysisOutcome:
        shared_metadata = dict(metadata or {})
        node_origins = origins_from_graph_nodes(graph)
        node_report = analyze_accessibility(
            graph,
            service_nodes_by_category,
            node_origins,
            threshold_minutes=self.threshold_minutes,
            include_details=include_details,
            metadata={**shared_metadata, "origin": node_origins.metadata},
        )

        if population_origins is None:
            return AnalysisOutcome(
                primary_report=node_report,
                node_report=node_report,
            )

        if population_origins.weight_unit != "population":
            raise ValueError("population origins must use 'population' as weight_unit")

        population_report = analyze_accessibility(
            graph,
            service_nodes_by_category,
            population_origins,
            threshold_minutes=self.threshold_minutes,
            include_details=include_details,
            metadata={**shared_metadata, "origin": population_origins.metadata},
        )
        comparison = compare_accessibility(population_report, node_report)
        return AnalysisOutcome(
            primary_report=population_report,
            node_report=node_report,
            population_report=population_report,
            comparison=comparison,
        )
