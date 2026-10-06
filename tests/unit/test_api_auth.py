import pytest
from fastapi import HTTPException

from fifteen_minute_city.api.app import app
from fifteen_minute_city.api.auth import configured_api_keys, require_api_key


def test_api_requires_configured_authentication(monkeypatch) -> None:
    monkeypatch.delenv("API_KEYS", raising=False)

    with pytest.raises(HTTPException) as error:
        require_api_key(None)

    assert error.value.status_code == 503


def test_api_rejects_missing_or_invalid_key(monkeypatch) -> None:
    monkeypatch.setenv("API_KEYS", "first-key,second-key")

    with pytest.raises(HTTPException) as missing:
        require_api_key(None)
    with pytest.raises(HTTPException) as invalid:
        require_api_key("wrong")

    assert missing.value.status_code == 401
    assert invalid.value.status_code == 401


def test_api_accepts_any_configured_key(monkeypatch) -> None:
    monkeypatch.setenv("API_KEYS", "first-key, second-key")

    assert configured_api_keys() == ("first-key", "second-key")
    assert require_api_key("second-key") == "second-key"


def test_openapi_describes_health_api_key_and_metric_routes() -> None:
    schema = app.openapi()

    assert "/health" in schema["paths"]
    security_scheme = schema["components"]["securitySchemes"]["ApiKeyAuth"]
    assert security_scheme["type"] == "apiKey"
    assert security_scheme["name"] == "X-API-Key"
    assert (
        "/api/v1/cities/{city_id}/latest/{strategy}/{category}/{metric}"
        in schema["paths"]
    )
    assert (
        "/api/v1/cities/{city_id}/history/{strategy}/{category}/{metric}"
        in schema["paths"]
    )
