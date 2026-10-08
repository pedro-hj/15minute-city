"""Transactional admission control for public, rate-limited analysis requests."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import math
import os
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from fifteen_minute_city.db.models.analysis_request import AnalysisRequest
from fifteen_minute_city.db.models.city import City
from fifteen_minute_city.db.models.execution import Execution

ADMISSION_LOCK = 202610080001


@lru_cache(maxsize=1)
def request_session_factory() -> sessionmaker:
    url = os.getenv("ANALYSES_DATABASE_URL")
    if not url:
        raise HTTPException(503, "Public analysis requests are not configured")
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return sessionmaker(
        create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=0),
        autoflush=False,
    )


def _requester_hash(client_ip: str) -> str:
    secret = os.getenv("ANALYSES_IP_HMAC_SECRET", "")
    if len(secret) < 32:
        raise HTTPException(503, "Public analysis protection is not configured")
    try:
        normalized = ipaddress.ip_address(client_ip).compressed
    except ValueError as exc:
        raise HTTPException(503, "Client network identity is unavailable") from exc
    return hmac.new(secret.encode(), normalized.encode(), hashlib.sha256).hexdigest()


def _seconds(name: str, default: int, minimum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise HTTPException(503, "Invalid analyses server configuration") from exc
    if value < minimum:
        raise HTTPException(503, "Invalid analyses server configuration")
    return value


def _serialize(job: AnalysisRequest) -> dict:
    return {
        "request_id": job.id,
        "ibge_code": job.ibge_code,
        "city": job.city_name,
        "state": job.state_name,
        "status": job.status,
        "requested_at": job.requested_at,
        "city_id": job.result_city_id,
        "results_url": (
            f"/api/v1/cities/{job.result_city_id}/latest"
            if job.status == "completed" and job.result_city_id is not None
            else None
        ),
    }


def submit(
    ibge_code: str,
    city_name: str,
    state_name: str,
    client_ip: str,
) -> tuple[dict, int]:
    """Allow one new job per client per hour; reuse active or complete analyses."""
    token = _requester_hash(client_ip)
    window = _seconds("ANALYSES_RATE_LIMIT_SECONDS", 3600, 60)
    capacity = _seconds("ANALYSES_QUEUE_MAX", 10, 1)
    now = datetime.now(timezone.utc)
    with request_session_factory().begin() as db:
        # One transaction-scoped PostgreSQL lock serializes all admissions.
        # Guarantees rate limits, capacity and duplicate checks across API workers.
        db.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": ADMISSION_LOCK})

        city = db.scalar(select(City).where(City.ibge_code == ibge_code))
        if city is not None:
            finished = db.scalar(
                select(Execution.id)
                .where(Execution.city_id == city.id, Execution.status == "completed")
                .limit(1)
            )
            if finished is not None:
                return {
                    "request_id": None,
                    "ibge_code": ibge_code,
                    "city": city.name,
                    "state": city.state,
                    "status": "completed",
                    "requested_at": None,
                    "city_id": city.id,
                    "results_url": f"/api/v1/cities/{city.id}/latest",
                }, 200

        active = db.scalar(
            select(AnalysisRequest)
            .where(
                AnalysisRequest.ibge_code == ibge_code,
                AnalysisRequest.status.in_(("queued", "processing")),
            )
            .order_by(AnalysisRequest.requested_at.desc())
            .limit(1)
        )
        if active is not None:
            return _serialize(active), 202

        recent = db.scalar(
            select(AnalysisRequest)
            .where(
                AnalysisRequest.requester_hash == token,
                AnalysisRequest.requested_at >= now - timedelta(seconds=window),
            )
            .order_by(AnalysisRequest.requested_at.desc())
            .limit(1)
        )
        if recent is not None:
            remainder = window - (now - recent.requested_at).total_seconds()
            raise HTTPException(
                status_code=429,
                detail="Only one new analysis request is allowed per hour",
                headers={"Retry-After": str(max(1, math.ceil(remainder)))},
            )

        count = db.scalar(
            select(func.count()).select_from(AnalysisRequest).where(
                AnalysisRequest.status.in_(("queued", "processing"))
            )
        )
        if count is not None and count >= capacity:
            raise HTTPException(
                503,
                "Analysis queue is full; try again later",
                headers={"Retry-After": "300"},
            )

        job = AnalysisRequest(
            id=str(uuid.uuid4()),
            ibge_code=ibge_code,
            city_name=city_name,
            state_name=state_name,
            requester_hash=token,
            status="queued",
            requested_at=now,
        )
        db.add(job)
        db.flush()
        return _serialize(job), 202


def request_status(request_id: str) -> dict:
    try:
        uid = str(uuid.UUID(request_id))
    except ValueError as exc:
        raise HTTPException(404, "Analysis request not found") from exc
    with request_session_factory()() as db:
        request = db.get(AnalysisRequest, uid)
        if request is None:
            raise HTTPException(404, "Analysis request not found")
        return _serialize(request)
