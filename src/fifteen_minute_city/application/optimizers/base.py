from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from fifteen_minute_city.application.server_simulation import SimulationBundle


@dataclass(frozen=True, slots=True)
class ProposedLocation:
    """Represents an optimal point suggested for the deployment of a service.

    Attributes:
        rank: Ordinal position of recommendation (1 = highest priority / biggest gain).
        node_id: Indentifier of the corresponding node in the walkable network.
        latitude: Geographical latitude in decimal degrees (WGS 84 / EPSG:4326).
        longitude: Geographical longitude in decimal degrees (WGS 84 / EPSG:4326).
        marginal_population: Absolute quantity of unattended population.
    """

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
    """Consolidated result of essencial services optimzation.

    Attributes:
        strategy: Name of the algorithm used for optimization (ex: 'greedy', 'milp').
        category: Category of service analyzed (ex: 'health', 'education').
        locations: Ordered collection of points recommended by the algorithm.
        baseline_coverage_percentage: Portion of the city's total population covered before the intervention (0.0 to 100.0%).
        simulated_coverage_percentage: Portion of the city's total population covered after the inclusion of k new suggested points (0.0 to 100.0%).
        execution_time_seconds: Execution time in seconds.
    """

    strategy: str  # TODO: Could define a default algorithm later.
    category: str
    locations: tuple[ProposedLocation, ...]
    baseline_coverage_percentage: float
    simulated_coverage_percentage: float
    execution_time_seconds: float

    @property
    def coverage_delta_percentage_points(self) -> float:
        """Populational coverage liquid gain in percentage points (p.p.)."""
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
        """Execute optimization and returns structured result.

        Args:
            Bundle: FMC1 simulation package containg the network graph, baseline times and population distribution per node.
            category: Service category to be optimized ('health', 'food' etc).
            k: Number of new facilities to be recommended (default: 1).
            threshold_minutes: Maximum walking threshold in minutes. If None, utilizes the original value from the bundle's metadata.
            min_distance_m: Miminum distance in meters between any two new suggested points (avoids excessive overlap/cannibalization).

        Returns:
            OptimizationResult containing new ideal points and coverage gains.

        Raises:
            ValueError: If category does not exist on bundle or if k < 1.
        """
