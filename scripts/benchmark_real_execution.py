from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from fifteen_minute_city.constants import SERVICE_CATEGORIES
from fifteen_minute_city.core.modules.locales import Region
from fifteen_minute_city.infrastructure.performance import (
    ProcessTreeProfiler,
    collect_hardware_information,
)
from fifteen_minute_city.main import format_output, resolve_output_path, write_result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark a complete analysis using real local data."
    )
    parser.add_argument("--city", default="Praia Grande")
    parser.add_argument("--state", default="São Paulo")
    parser.add_argument("--country", default="Brazil")
    parser.add_argument(
        "--pbf", type=Path, default=Path("data/input/brazil-260922.osm.pbf")
    )
    parser.add_argument(
        "--population-grid", type=Path, default=Path("data/input/grade_id25.zip")
    )
    parser.add_argument("--population-column", default="TOTAL")
    parser.add_argument("--population-id-column", default="ID_UNICO")
    parser.add_argument("--boundary", type=Path)
    parser.add_argument("--cache-dir", type=Path, default=Path("data/cache"))
    parser.add_argument("--speed-kmh", type=float, default=3.0)
    parser.add_argument("--threshold-minutes", type=float, default=15.0)
    parser.add_argument(
        "--services", nargs="+", choices=SERVICE_CATEGORIES, default=None
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def _validate_input(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")


def _measure_stage[T](
    stages: dict[str, dict[str, float]],
    name: str,
    operation: Callable[[], T],
) -> T:
    print(f"Measuring: {name}")
    with ProcessTreeProfiler() as profiler:
        result = operation()
    stages[name] = profiler.result().to_dict()
    return result


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _validate_input(args.pbf, "PBF")
    _validate_input(args.population_grid, "population grid")
    if args.boundary is not None:
        _validate_input(args.boundary, "boundary")

    started_at = datetime.now().astimezone()
    locale = {"city": args.city, "state": args.state, "country": args.country}
    stages: dict[str, dict[str, float]] = {}

    with ProcessTreeProfiler() as total_profiler:
        region = Region(
            locale,
            speed=args.speed_kmh,
            pbf_path=args.pbf,
            threshold_minutes=args.threshold_minutes,
            cache_dir=args.cache_dir,
            boundary_path=args.boundary,
        )
        _measure_stage(stages, "graph", region.build_graph)
        _measure_stage(
            stages,
            "services",
            lambda: region.locate_services(args.services),
        )
        origins = _measure_stage(
            stages,
            "population_grid",
            lambda: region.load_population_grid(
                str(args.population_grid),
                population_column=args.population_column,
                id_column=args.population_id_column,
            ),
        )
        outcome = _measure_stage(
            stages,
            "accessibility_calculation",
            region.calculate_accessibility,
        )
        _measure_stage(
            stages,
            "result_serialization",
            lambda: json.dumps(
                format_output(outcome, locale=locale, output_mode="detailed"),
                ensure_ascii=False,
            ),
        )

    finished_at = datetime.now().astimezone()
    graph_artifact = region._graph_artifact
    total_measurement = total_profiler.result().to_dict()
    total_measurement["ram_peak_mib"] = max(
        total_measurement["ram_peak_mib"],
        *(stage["ram_peak_mib"] for stage in stages.values()),
    )
    report: dict[str, Any] = {
        "benchmark": "real_end_to_end_execution",
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "location": locale,
        "configuration": {
            "speed_kmh": args.speed_kmh,
            "threshold_minutes": args.threshold_minutes,
            "categories": args.services or list(SERVICE_CATEGORIES),
            "population_column": args.population_column,
            "population_id_column": args.population_id_column,
            "graph_cache_hit": graph_artifact.cache_hit if graph_artifact else None,
            "population_origins": len(origins.origins),
            "population_total": origins.total_weight,
        },
        "inputs": {
            "pbf": {
                "path": str(args.pbf.resolve()),
                "size_mib": round(args.pbf.stat().st_size / (1024**2), 3),
            },
            "population_grid": {
                "path": str(args.population_grid.resolve()),
                "size_mib": round(args.population_grid.stat().st_size / (1024**2), 3),
            },
            "boundary": str(args.boundary.resolve()) if args.boundary else "geocoder",
        },
        "hardware": collect_hardware_information(),
        "stages": stages,
        "total": total_measurement,
    }

    output = args.output or resolve_output_path(
        Path("data/output/benchmarks"),
        city=args.city,
        state=args.state,
        country=args.country,
        generated_at=started_at,
    )
    write_result(
        output,
        json.dumps(report, ensure_ascii=False, indent=2),
        overwrite=args.overwrite,
    )
    print(f"Benchmark saved at {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
