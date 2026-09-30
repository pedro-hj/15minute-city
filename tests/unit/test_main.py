from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from fifteen_minute_city.main import _slugify, resolve_output_path, write_result


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


def test_write_result(tmp_path):
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
