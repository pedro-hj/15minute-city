"""Public API for safely queuing expensive municipal analyses."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from fifteen_minute_city.api.analysis_service import request_status, submit
from fifteen_minute_city.infrastructure.ibge import (
    IbgeUnavailable,
    municipality_by_code,
)


class AnalysisSubmission(BaseModel):
    ibge_code: str = Field(pattern=r"^[0-9]{7}$")


router = APIRouter(prefix="/api/v1/analyses", tags=["analyses"])


@router.post("", status_code=202)
def request_analysis(body: AnalysisSubmission, request: Request, response: Response):
    """A successful admission is rate limited; duplicate city requests are reused."""
    client_ip = request.client.host if request.client is not None else ""
    if not client_ip:
        raise HTTPException(503, "Client network identity is unavailable")
    try:
        name, state = municipality_by_code(body.ibge_code)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except IbgeUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    result, status_code = submit(body.ibge_code, name, state, client_ip)
    response.status_code = status_code
    return result


@router.get("/{request_id}")
def get_analysis_status(request_id: str):
    return request_status(request_id)
