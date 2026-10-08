"""Public API for safely queuing expensive municipal analyses."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator

from fifteen_minute_city.api.analysis_service import request_status, submit
from fifteen_minute_city.infrastructure.ibge import (
    IbgeUnavailable,
    municipality_by_location,
)


class AnalysisSubmission(BaseModel):
    city: str = Field(min_length=1, max_length=120)
    state: str = Field(min_length=1, max_length=100)
    country: str = Field(min_length=2, max_length=60)

    @field_validator("city", "state", "country")
    @classmethod
    def clean_location(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Location fields must not be blank")
        return value


router = APIRouter(prefix="/api/v1/analyses", tags=["analyses"])


@router.post("", status_code=202)
def request_analysis(body: AnalysisSubmission, request: Request, response: Response):
    """Resolve names to official codes; rate-limit only newly admitted jobs."""
    client_ip = request.client.host if request.client is not None else ""
    if not client_ip:
        raise HTTPException(503, "Client network identity is unavailable")
    try:
        code, city, state = municipality_by_location(
            body.city, body.state, body.country
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except IbgeUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    result, status_code = submit(code, city, state, client_ip)
    response.status_code = status_code
    return result


@router.get("/{request_id}")
def get_analysis_status(request_id: str):
    return request_status(request_id)
