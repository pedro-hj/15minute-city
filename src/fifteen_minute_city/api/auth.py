import os
import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(
    name="X-API-Key",
    scheme_name="ApiKeyAuth",
    description="API key supplied by the 15-minute city service.",
    auto_error=False,
)


def configured_api_keys() -> tuple[str, ...]:
    """Read the comma-separated API keys without caching environment state."""
    return tuple(
        key.strip() for key in os.getenv("API_KEYS", "").split(",") if key.strip()
    )


def require_api_key(api_key: str | None = Security(api_key_header)) -> str:
    """Require a key configured through API_KEYS."""
    valid_keys = configured_api_keys()
    if not valid_keys:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication is not configured",
        )
    if api_key is None or not any(
        secrets.compare_digest(api_key, valid_key) for valid_key in valid_keys
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return api_key
