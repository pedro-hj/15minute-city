from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any


@dataclass(frozen=True, slots=True)
class Origin:
    """Weighted analysis origin associated with a node in the walking graph."""

    origin_id: str
    node_id: int
    weight: float

    def __post_init__(self) -> None:
        if not self.origin_id:
            raise ValueError("origin_id must not be empty")
        if self.weight <= 0 or not isfinite(self.weight):
            raise ValueError("origin weight must be a finite value greater than zero")


@dataclass(frozen=True, slots=True)
class OriginSet:
    """Origins analyzed with a common weighting strategy."""

    strategy: str
    weight_unit: str
    origins: tuple[Origin, ...]
    source: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.strategy:
            raise ValueError("origin strategy must not be empty")
        if not self.weight_unit:
            raise ValueError("weight_unit must not be empty")
        if not self.origins:
            raise ValueError("at least one origin is required")
        origin_ids = [origin.origin_id for origin in self.origins]
        if len(origin_ids) != len(set(origin_ids)):
            raise ValueError("origin IDs must be unique")

    @property
    def total_weight(self) -> float:
        return sum(origin.weight for origin in self.origins)


@dataclass(frozen=True, slots=True)
class OriginAccessibility:
    """Raw accessibility result for one origin and one service category."""

    origin: Origin
    travel_time_minutes: float | None
    nearest_service_node_id: int | None

    def __post_init__(self) -> None:
        if self.travel_time_minutes is not None and (
            self.travel_time_minutes < 0 or not isfinite(self.travel_time_minutes)
        ):
            raise ValueError("travel time must be finite and non-negative")
        if (self.travel_time_minutes is None) != (self.nearest_service_node_id is None):
            raise ValueError(
                "travel time and nearest service node must both be present or absent"
            )

    @property
    def origin_id(self) -> str:
        return self.origin.origin_id

    @property
    def node_id(self) -> int:
        return self.origin.node_id

    @property
    def weight(self) -> float:
        return self.origin.weight

    @property
    def reachable(self) -> bool:
        return self.travel_time_minutes is not None

    def is_within(self, threshold_minutes: float) -> bool:
        if threshold_minutes <= 0 or not isfinite(threshold_minutes):
            raise ValueError("threshold must be a finite value greater than zero")
        return (
            self.travel_time_minutes is not None
            and self.travel_time_minutes <= threshold_minutes
        )


@dataclass(frozen=True, slots=True)
class CategoryAccessibility:
    """Aggregated accessibility indicators for one essential-service category."""

    category: str
    threshold_minutes: float
    total_weight: float
    reachable_weight: float
    within_threshold_weight: float
    mean_travel_time_minutes: float | None
    median_travel_time_minutes: float | None
    details: tuple[OriginAccessibility, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.category:
            raise ValueError("category must not be empty")
        if self.threshold_minutes <= 0 or not isfinite(self.threshold_minutes):
            raise ValueError("threshold must be a finite value greater than zero")
        if self.total_weight <= 0 or not isfinite(self.total_weight):
            raise ValueError("total weight must be a finite value greater than zero")
        if not 0 <= self.within_threshold_weight <= self.reachable_weight:
            raise ValueError("within-threshold weight must not exceed reachable weight")
        if not self.reachable_weight <= self.total_weight:
            raise ValueError("reachable weight must not exceed total weight")
        for value in (
            self.mean_travel_time_minutes,
            self.median_travel_time_minutes,
        ):
            if value is not None and (value < 0 or not isfinite(value)):
                raise ValueError(
                    "travel-time statistics must be finite and non-negative"
                )

    @property
    def unreachable_weight(self) -> float:
        return self.total_weight - self.reachable_weight

    @property
    def coverage_percentage(self) -> float:
        return round(100.0 * self.within_threshold_weight / self.total_weight, 6)

    @property
    def unreachable_percentage(self) -> float:
        return round(100.0 * self.unreachable_weight / self.total_weight, 6)


@dataclass(frozen=True, slots=True)
class AccessibilityReport:
    """Complete accessibility result for one origin-weighting strategy."""

    origin_strategy: str
    weight_unit: str
    threshold_minutes: float
    total_weight: float
    categories: dict[str, CategoryAccessibility]
    overall_within_threshold_weight: float
    overall_unreachable_weight: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.origin_strategy:
            raise ValueError("origin strategy must not be empty")
        if not self.weight_unit:
            raise ValueError("weight unit must not be empty")
        if self.threshold_minutes <= 0 or not isfinite(self.threshold_minutes):
            raise ValueError("threshold must be a finite value greater than zero")
        if self.total_weight <= 0 or not isfinite(self.total_weight):
            raise ValueError("total weight must be a finite value greater than zero")
        if not self.categories:
            raise ValueError("at least one category result is required")
        if not 0 <= self.overall_within_threshold_weight <= self.total_weight:
            raise ValueError("overall within-threshold weight is inconsistent")
        if not 0 <= self.overall_unreachable_weight <= self.total_weight:
            raise ValueError("overall unreachable weight is inconsistent")
        for code, result in self.categories.items():
            if code != result.category:
                raise ValueError("category key must match the category result")
            if result.total_weight != self.total_weight:
                raise ValueError("all categories must use the report total weight")
            if result.threshold_minutes != self.threshold_minutes:
                raise ValueError("all categories must use the report threshold")

    @property
    def overall_coverage_percentage(self) -> float:
        return round(
            100.0 * self.overall_within_threshold_weight / self.total_weight,
            6,
        )

    @property
    def overall_unreachable_percentage(self) -> float:
        return round(100.0 * self.overall_unreachable_weight / self.total_weight, 6)

    def to_dict(self, *, include_details: bool = False) -> dict[str, Any]:
        categories = {}
        for code, result in self.categories.items():
            category_data: dict[str, Any] = {
                "category": result.category,
                "total_weight": result.total_weight,
                "reachable_weight": result.reachable_weight,
                "within_threshold_weight": result.within_threshold_weight,
                "unreachable_weight": result.unreachable_weight,
                "coverage_percentage": result.coverage_percentage,
                "unreachable_percentage": result.unreachable_percentage,
                "mean_travel_time_minutes": result.mean_travel_time_minutes,
                "median_travel_time_minutes": result.median_travel_time_minutes,
            }
            if include_details:
                category_data["details"] = [
                    {
                        "origin_id": detail.origin_id,
                        "node_id": detail.node_id,
                        "weight": detail.weight,
                        "travel_time_minutes": detail.travel_time_minutes,
                        "reachable": detail.reachable,
                        "within_threshold": detail.is_within(result.threshold_minutes),
                        "nearest_service_node_id": detail.nearest_service_node_id,
                    }
                    for detail in result.details
                ]
            categories[code] = category_data

        return {
            "origin_strategy": self.origin_strategy,
            "weight_unit": self.weight_unit,
            "threshold_minutes": self.threshold_minutes,
            "total_weight": self.total_weight,
            "categories": categories,
            "overall_coverage_percentage": self.overall_coverage_percentage,
            "overall_unreachable_percentage": self.overall_unreachable_percentage,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class AccessibilityComparison:
    """Comparison between population-weighted and graph-node reports."""

    population_report: AccessibilityReport
    node_report: AccessibilityReport

    def __post_init__(self) -> None:
        if set(self.population_report.categories) != set(self.node_report.categories):
            raise ValueError("reports must contain the same service categories")
        if (
            self.population_report.threshold_minutes
            != self.node_report.threshold_minutes
        ):
            raise ValueError("reports must use the same accessibility threshold")

    @property
    def category_coverage_delta(self) -> dict[str, float]:
        return {
            category: round(
                self.population_report.categories[category].coverage_percentage
                - self.node_report.categories[category].coverage_percentage,
                6,
            )
            for category in self.population_report.categories
        }

    @property
    def category_unreachable_delta(self) -> dict[str, float]:
        return {
            category: round(
                self.population_report.categories[category].unreachable_percentage
                - self.node_report.categories[category].unreachable_percentage,
                6,
            )
            for category in self.population_report.categories
        }

    @property
    def overall_coverage_delta(self) -> float:
        return round(
            self.population_report.overall_coverage_percentage
            - self.node_report.overall_coverage_percentage,
            6,
        )

    @property
    def overall_unreachable_delta(self) -> float:
        return round(
            self.population_report.overall_unreachable_percentage
            - self.node_report.overall_unreachable_percentage,
            6,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "calculation": "population_report - node_report",
            "unit": "percentage_points",
            "category_coverage_delta": self.category_coverage_delta,
            "category_unreachable_delta": self.category_unreachable_delta,
            "overall_coverage_delta": self.overall_coverage_delta,
            "overall_unreachable_delta": self.overall_unreachable_delta,
        }
