from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from fifteen_minute_city.application.server_simulation import SimulationBundle


@dataclass(frozen=True, slots=True)
class ProposedLocation:
    """Represents an optimal point suggested for the deployment of a service."""

    rank: int
    node_id: int
    latitude: float
    longitude: float
    marginal_population: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "node_id": self.node_id,
            "latitude": round(self.latitude, 6),
            "longitude": round(self.longitude, 6),
            "marginal_population": round(self.marginal_population, 2),
        }


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    """Consolidated result of essencial services optimzation."""

    strategy: str
    category: str
    locations: tuple[ProposedLocation, ...]
    baseline_coverage_percentage: float
    simulated_coverage_percentage: float
    execution_time_seconds: float

    @property
    def coverage_delta_percentage_points(self) -> float:
        return round(
            self.simulated_coverage_percentage - self.baseline_coverage_percentage, 6
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "category": self.category,
            "locations": [loc.to_dict() for loc in self.locations],
            "baseline_coverage_percentage": round(self.baseline_coverage_percentage, 4),
            "simulated_coverage_percentage": round(
                self.simulated_coverage_percentage, 4
            ),
            "coverage_delta_percentage_points": self.coverage_delta_percentage_points,
            "execution_time_seconds": round(self.execution_time_seconds, 4),
        }


class BaseLocationOptimizer(ABC):
    """Base contract for all optimization algorithms."""

    @abstractmethod
    def optimize(
        self,
        bundle: SimulationBundle,
        category: str,
        k: int = 1,
        *,
        threshold_minutes: float | None = None,
        min_distance_m: float = 0.0,
    ) -> OptimizationResult:
        """Execute optimization and returns structured result."""
