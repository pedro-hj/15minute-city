"""Publicly requested analysis jobs, separate from computational executions."""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from fifteen_minute_city.db.base import Base


class AnalysisRequest(Base):
    __tablename__ = "analysis_request"
    __table_args__ = (
        Index(
            "uq_analysis_request_active_city",
            "ibge_code",
            unique=True,
            postgresql_where=text("status IN ('queued', 'processing')"),
        ),
        Index("ix_analysis_request_requester_time", "requester_hash", "requested_at"),
        Index("ix_analysis_request_status_time", "status", "requested_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ibge_code: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    city_name: Mapped[str] = mapped_column(String(255), nullable=False)
    state_name: Mapped[str] = mapped_column(String(100), nullable=False)
    requester_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    requested_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    result_city_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("city.id", ondelete="SET NULL"), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(String(512))
