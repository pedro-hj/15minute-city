from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AnalysisSettings:
    """Validated filesystem and algorithm parameters for one analysis."""

    pbf_path: Path
    cache_dir: Path
    boundary_path: Path | None = None
    population_grid_path: Path | None = None
    population_column: str = "population"
    population_id_column: str | None = None
    network_type: str = "walk"
    speed_kmh: float = 3.0
    threshold_minutes: float = 15.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "pbf_path", Path(self.pbf_path).expanduser().resolve())
        object.__setattr__(
            self,
            "cache_dir",
            Path(self.cache_dir).expanduser().resolve(),
        )
        if self.population_grid_path is not None:
            object.__setattr__(
                self,
                "population_grid_path",
                Path(self.population_grid_path).expanduser().resolve(),
            )
        if self.boundary_path is not None:
            object.__setattr__(
                self,
                "boundary_path",
                Path(self.boundary_path).expanduser().resolve(),
            )
        if self.network_type != "walk":
            raise ValueError("only the 'walk' network type is currently supported")
        if self.speed_kmh <= 0 or not isfinite(self.speed_kmh):
            raise ValueError("speed_kmh must be a finite value greater than zero")
        if self.threshold_minutes <= 0 or not isfinite(self.threshold_minutes):
            raise ValueError(
                "threshold_minutes must be a finite value greater than zero"
            )
        if not self.population_column:
            raise ValueError("population_column must not be empty")
