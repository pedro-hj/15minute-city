from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from fifteen_minute_city.main import (
    _slugify,
    build_parser,
    format_output,
    main,
    resolve_output_path,
    write_result,
)


@pytest.mark.parametrize(
    ("original", "expected"),
    [
        ("Praia Grande", "praia-grande"),
        ("São Paulo", "sao-paulo"),
        (" Rio de  Janeiro ", "rio-de-janeiro"),
        ("Belo_Horizonte", "belo-horizonte"),
        ("---", "unknown"),
    ],
)
def test_slugify(original: str, expected: str) -> None:
    result = _slugify(original)

    assert result == expected


@pytest.mark.parametrize(
    ("output", "city", "state", "country", "generated_at", "expected"),
    [
        (
            None,
            "Praia Grande",
            "São Paulo",
            "Brazil",
            datetime(2026, 12, 25, 15, 30, 0, tzinfo=ZoneInfo("America/Sao_Paulo")),
            Path("data/output/praia-grande-sao-paulo/20261225T153000-0300.json"),
        ),
        (
            Path("resultados/testes"),
            "São José do Rio Preto",
            None,
            "Brazil",
            datetime(2026, 12, 25, 15, 30, 0, tzinfo=ZoneInfo("America/Sao_Paulo")),
            Path(
                "resultados/testes/sao-jose-do-rio-preto-brazil/20261225T153000-0300.json"
            ),
        ),
        (
            Path("resultados/testes/meu-arquivo.json"),
            "São José do Rio Preto",
            "São Paulo",
            "Brazil",
            datetime(2026, 12, 25, 15, 30, 0, tzinfo=ZoneInfo("America/Sao_Paulo")),
            Path("resultados/testes/meu-arquivo.json"),
        ),
    ],
)
def test_resolve_output_path(
    expected: Path,
    output: Path | None,
    city: str,
    state: str | None,
    country: str,
    generated_at: datetime | None,
) -> None:
    result = resolve_output_path(
        output,
        city=city,
        state=state,
        country=country,
        generated_at=generated_at,
    )

    assert result == expected


def test_write_result(tmp_path) -> None:
    my_dir = tmp_path / "results/tests" / "test.json"
    data = "São Paulo"
    data2 = "Maranhão"

    write_result(my_dir, data)

    assert my_dir.parent.resolve().is_dir()
    assert my_dir.is_file()

    with pytest.raises(FileExistsError):
        write_result(my_dir, data, overwrite=False)

    assert my_dir.read_text("utf-8") == data + "\n"

    write_result(my_dir, data2, overwrite=True)

    assert my_dir.read_text("utf-8") == data2 + "\n"


def test_main_mandatory_arguments() -> None:
    with pytest.raises(SystemExit) as error:
        main([])

    assert error.value.code == 2


def test_parser_accepts_service_categories() -> None:
    args = build_parser().parse_args(
        [
            "--city",
            "Praia Grande",
            "--pbf",
            "data/input/brazil.osm.pbf",
            "--population-grid",
            "data/input/grade.zip",
            "--services",
            "health",
            "food",
        ]
    )

    assert args.services == ["health", "food"]


def test_format_output_simple_uses_only_population_scores() -> None:
    population_report = SimpleNamespace(
        categories={
            "health": SimpleNamespace(coverage_percentage=82.5),
            "education": SimpleNamespace(coverage_percentage=71.0),
        },
        overall_coverage_percentage=64.25,
    )
    outcome = SimpleNamespace(
        population_report=population_report,
        comparison=object(),
    )
    locale = {"city": "Praia Grande", "state": "São Paulo", "country": "Brazil"}

    result = format_output(outcome, locale=locale, output_mode="simple")

    assert result == {
        "location": locale,
        "category_results": {"health": 82.5, "education": 71.0},
        "overall_result": 64.25,
    }
    assert "comparison" not in result


def test_format_output_detailed_preserves_complete_outcome() -> None:
    expected = {
        "comparison": {
            "calculation": "population_report - node_report",
            "unit": "percentage_points",
            "overall_coverage_delta": -4.5,
        }
    }
    outcome = SimpleNamespace(to_dict=lambda: expected)

    result = format_output(
        outcome,
        locale={"city": "Praia Grande", "country": "Brazil"},
        output_mode="detailed",
    )

    assert result == expected
