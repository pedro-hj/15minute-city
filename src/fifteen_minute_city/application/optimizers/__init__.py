from fifteen_minute_city.application.optimizers.base import (
    BaseLocationOptimizer,
    OptimizationResult,
    ProposedLocation,
)
from fifteen_minute_city.application.optimizers.greedy import GreedyLocationOptimizer

DEFAULT_STRATEGY = "greedy"


def create_optimizer(strategy: str = DEFAULT_STRATEGY) -> BaseLocationOptimizer:
    """Create a location optimizer, using the greedy strategy by default."""
    if strategy == DEFAULT_STRATEGY:
        return GreedyLocationOptimizer()
    raise ValueError(f"Unknown optimization strategy: {strategy}")


__all__ = [
    "DEFAULT_STRATEGY",
    "BaseLocationOptimizer",
    "GreedyLocationOptimizer",
    "OptimizationResult",
    "ProposedLocation",
    "create_optimizer",
]
