"""Validate Brazilian municipal codes against the IBGE localities API."""

from __future__ import annotations

import json
from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class IbgeUnavailable(Exception):
    """The official municipality metadata service is unavailable."""


@lru_cache(maxsize=4096)
def municipality_by_code(ibge_code: str) -> tuple[str, str]:
    if len(ibge_code) != 7 or not ibge_code.isascii() or not ibge_code.isdigit():
        raise ValueError("Invalid seven-digit IBGE municipality code")
    url = (
        "https://servicodados.ibge.gov.br/api/v1/localidades/"
        f"municipios/{ibge_code}"
    )
    try:
        with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=8) as response:
            data = response.read(64_001)
    except HTTPError as exc:
        if exc.code == 404:
            raise ValueError("IBGE municipality code not found") from exc
        raise IbgeUnavailable("IBGE metadata service returned an HTTP error") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise IbgeUnavailable("IBGE metadata service unavailable") from exc

    if len(data) > 64_000:
        raise IbgeUnavailable("IBGE metadata response too large")
    try:
        entry = json.loads(data)
        if not isinstance(entry, dict) or str(entry["id"]) != ibge_code:
            raise ValueError("IBGE municipality code not found")
        state = entry["microrregiao"]["mesorregiao"]["UF"]["nome"]
        city = entry["nome"]
        if not city or not state:
            raise KeyError("municipality or state")
        return str(city), str(state)
    except (TypeError, KeyError, json.JSONDecodeError) as exc:
        raise IbgeUnavailable("Unexpected IBGE metadata response") from exc
