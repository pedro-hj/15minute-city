from pathlib import Path

import pytest

from fifteen_minute_city.config import AnalysisSettings


def test_analysis_settings_resolve_paths(tmp_path: Path) -> None:
    settings = AnalysisSettings(
        pbf_path=tmp_path / "source.osm.pbf",
        cache_dir=tmp_path / "cache",
        boundary_path=tmp_path / "boundary.geojson",
        population_grid_path=tmp_path / "population.zip",
    )

    assert settings.pbf_path.is_absolute()
    assert settings.cache_dir.is_absolute()
    assert settings.boundary_path is not None
    assert settings.boundary_path.is_absolute()
    assert settings.population_grid_path is not None
    assert settings.population_grid_path.is_absolute()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("speed_kmh", 0),
        ("speed_kmh", float("inf")),
        ("threshold_minutes", 0),
        ("threshold_minutes", float("nan")),
    ],
)
def test_analysis_settings_reject_invalid_numbers(
    tmp_path: Path, field: str, value: float
) -> None:
    arguments = {
        "pbf_path": tmp_path / "source.osm.pbf",
        "cache_dir": tmp_path / "cache",
        field: value,
    }

    with pytest.raises(ValueError):
        AnalysisSettings(**arguments)
