"""Resolve Brazilian municipalities by city, state, and country.

User-facing requests do not need an IBGE code. The official IBGE code is
resolved internally and used as a stable identifier for deduplication.
"""

from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class IbgeUnavailable(Exception):
    """The official municipality metadata service is unavailable."""


STATE_NAMES = {
    "AC": "Acre",
    "AL": "Alagoas",
    "AP": "Amapá",
    "AM": "Amazonas",
    "BA": "Bahia",
    "CE": "Ceará",
    "DF": "Distrito Federal",
    "ES": "Espírito Santo",
    "GO": "Goiás",
    "MA": "Maranhão",
    "MT": "Mato Grosso",
    "MS": "Mato Grosso do Sul",
    "MG": "Minas Gerais",
    "PA": "Pará",
    "PB": "Paraíba",
    "PR": "Paraná",
    "PE": "Pernambuco",
    "PI": "Piauí",
    "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul",
    "RO": "Rondônia",
    "RR": "Roraima",
    "SC": "Santa Catarina",
    "SP": "São Paulo",
    "SE": "Sergipe",
    "TO": "Tocantins",
}


def _normal(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.strip())
    return "".join(
        ch for ch in normalized if not unicodedata.combining(ch)
    ).casefold()


def _state_uf(state: str) -> str:
    normalized = _normal(state)
    matches = [
        uf for uf, name in STATE_NAMES.items()
        if normalized in (_normal(uf), _normal(name))
    ]
    if len(matches) != 1:
        raise ValueError("Brazilian state not recognized")
    return matches[0]


def _fetch_json(url: str, max_bytes: int) -> object:
    try:
        with urlopen(
            Request(url, headers={"Accept": "application/json"}),
            timeout=8,
        ) as response:
            data = response.read(max_bytes + 1)
    except HTTPError as exc:
        if exc.code == 404:
            raise ValueError("IBGE locality not found") from exc
        raise IbgeUnavailable("IBGE metadata service returned an HTTP error") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise IbgeUnavailable("IBGE metadata service unavailable") from exc
    if len(data) > max_bytes:
        raise IbgeUnavailable("IBGE metadata response too large")
    try:
        return json.loads(data)
    except (ValueError, UnicodeDecodeError) as exc:
        raise IbgeUnavailable("Unexpected IBGE metadata response") from exc


@lru_cache(maxsize=27)
def _municipalities_for_state(uf: str) -> tuple[tuple[str, str], ...]:
    # Fixed official host and whitelisted UF: no user-provided URLs.
    url = f"https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios"
    entries = _fetch_json(url, max_bytes=1_000_000)
    if not isinstance(entries, list) or not entries:
        raise IbgeUnavailable("Unexpected IBGE municipality list")
    results = []
    for item in entries:
        try:
            name = item["nome"]
            code = str(item["id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise IbgeUnavailable("Unexpected IBGE municipality entry") from exc
        if not isinstance(name, str) or not code.isascii() or not code.isdigit() or len(code) != 7:
            raise IbgeUnavailable("Unexpected IBGE municipality entry")
        results.append((name, code))
    return tuple(results)


def municipality_by_location(
    city: str, state: str, country: str
) -> tuple[str, str, str]:
    """Return (ibge_code, canonical_city, canonical_state) from named inputs.

    Only Brazilian municipalities are supported by the national OSM and
    population datasets deployed with this application.
    """
    if _normal(country) not in {"br", "brasil", "brazil"}:
        raise ValueError("Only cities in Brazil are currently supported")
    uf = _state_uf(state)
    target = _normal(city)
    if not target:
        raise ValueError("City name is required")
    matches = [
        (name, code) for name, code in _municipalities_for_state(uf)
        if _normal(name) == target
    ]
    if len(matches) != 1:
        raise ValueError("Municipality not found in the specified Brazilian state")
    canonical_name, ibge_code = matches[0]
    return ibge_code, canonical_name, STATE_NAMES[uf]


@lru_cache(maxsize=4096)
def municipality_by_code(ibge_code: str) -> tuple[str, str]:
    """Legacy internal lookup retained for consumers requiring an IBGE ID."""
    if len(ibge_code) != 7 or not ibge_code.isascii() or not ibge_code.isdigit():
        raise ValueError("Invalid seven-digit IBGE municipality code")
    entry = _fetch_json(
        f"https://servicodados.ibge.gov.br/api/v1/localidades/municipios/{ibge_code}",
        max_bytes=64_000,
    )
    try:
        if not isinstance(entry, dict) or str(entry["id"]) != ibge_code:
            raise ValueError("IBGE municipality code not found")
        state = entry["microrregiao"]["mesorregiao"]["UF"]["nome"]
        city = entry["nome"]
        if not city or not state:
            raise KeyError("municipality or state")
        return str(city), str(state)
    except (TypeError, KeyError) as exc:
        raise IbgeUnavailable("Unexpected IBGE metadata response") from exc
