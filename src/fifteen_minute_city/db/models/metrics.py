from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fifteen_minute_city.db.base import Base

if TYPE_CHECKING:
    from fifteen_minute_city.db.models.category import ServiceCategory
    from fifteen_minute_city.db.models.execution import Execution
    from fifteen_minute_city.db.models.node import Node
    from fifteen_minute_city.db.models.service import Service


class NodeReachability(Base):
    """
    Fact table storing detailed travel time measurements from each node to the nearest service per category.

    Serves as the high-volume source of truth for point-and-click UI queries.
    """

    __tablename__ = "node_reachability"

    node_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("node.id", ondelete="CASCADE"),
        primary_key=True,
        comment="Foreign key referencing the node (part of composite primary key)",
    )
    category_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("service_category.id", ondelete="CASCADE"),
        primary_key=True,
        comment="Foreign key referencing the service category (part of composite primary key)",
    )
    closest_service_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("service.id", ondelete="SET NULL"),
        nullable=True,
        comment="Foreign key to the specific closest service establishment identified",
    )
    travel_time_minutes: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Calculated time, or null when unreachable"
    )
    reachable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="Whether any route exists"
    )
    within_threshold: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Flag indicating if travel time is within the 15-minute threshold",
    )

    # Relationships
    node: Mapped[Node] = relationship("Node", back_populates="reachabilities")
    category: Mapped[ServiceCategory] = relationship(
        "ServiceCategory", back_populates="reachabilities"
    )
    closest_service: Mapped[Service] = relationship(
        "Service", back_populates="closest_for_reachabilities"
    )

    def __repr__(self) -> str:
        return (
            f"<NodeReachability(node_id={self.node_id}, category_id={self.category_id}, "
            f"time={self.travel_time_minutes}min, within_threshold={self.within_threshold})>"
        )


class CityIndex(Base):
    """
    Aggregated metrics and reachability indices per execution and service category.

    Serves as the core dataset for analytical dashboards and cross-city comparisons.
    """

    __tablename__ = "city_index"

    execution_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("execution.id", ondelete="CASCADE"),
        primary_key=True,
        comment="Foreign key referencing the execution (part of composite primary key)",
    )
    category_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("service_category.id", ondelete="CASCADE"),
        primary_key=True,
        comment="Foreign key referencing the service category (part of composite primary key)",
    )
    origin_strategy: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
        comment="Origin weighting strategy, such as population_grid or network_nodes",
    )
    weight_unit: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Meaning of the aggregate weights"
    )
    threshold_minutes: Mapped[float] = mapped_column(
        Float, nullable=False, comment="Accessibility threshold used by the analysis"
    )
    total_weight: Mapped[float] = mapped_column(
        Float, nullable=False, comment="Total population or node weight analyzed"
    )
    reachable_weight: Mapped[float] = mapped_column(
        Float, nullable=False, comment="Weight with any path to the category"
    )
    within_threshold_weight: Mapped[float] = mapped_column(
        Float, nullable=False, comment="Weight within the accessibility threshold"
    )
    unreachable_weight: Mapped[float] = mapped_column(
        Float, nullable=False, comment="Weight without a path to the category"
    )
    mean_travel_time_minutes: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Weighted mean time among reachable origins"
    )
    median_travel_time_minutes: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Weighted median time among reachable origins"
    )
    percentage_within_threshold: Mapped[float] = mapped_column(
        Float, nullable=False, comment="Weighted coverage within the threshold (0-100%)"
    )
    unreachable_percentage: Mapped[float] = mapped_column(
        Float, nullable=False, comment="Weighted percentage without a path (0-100%)"
    )
    overall_index: Mapped[float] = mapped_column(
        Float, nullable=False, comment="Category accessibility score from 0 to 100"
    )

    # Relationships
    execution: Mapped[Execution] = relationship(
        "Execution", back_populates="city_indices"
    )
    category: Mapped[ServiceCategory] = relationship(
        "ServiceCategory", back_populates="city_indices"
    )

    def __repr__(self) -> str:
        return (
            f"<CityIndex(execution_id={self.execution_id}, category_id={self.category_id}, "
            f"origin_strategy='{self.origin_strategy}', overall_index={self.overall_index})>"
        )


class AccessibilitySummary(Base):
    """Overall score requiring access to every essential service category."""

    __tablename__ = "accessibility_summary"

    execution_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("execution.id", ondelete="CASCADE"),
        primary_key=True,
    )
    origin_strategy: Mapped[str] = mapped_column(String(50), primary_key=True)
    weight_unit: Mapped[str] = mapped_column(String(50), nullable=False)
    threshold_minutes: Mapped[float] = mapped_column(Float, nullable=False)
    total_weight: Mapped[float] = mapped_column(Float, nullable=False)
    overall_coverage_percentage: Mapped[float] = mapped_column(Float, nullable=False)
    overall_unreachable_percentage: Mapped[float] = mapped_column(Float, nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)

    execution: Mapped[Execution] = relationship(
        "Execution", back_populates="accessibility_summaries"
    )

    def __repr__(self) -> str:
        return (
            f"<AccessibilitySummary(execution_id={self.execution_id}, "
            f"origin_strategy='{self.origin_strategy}', score={self.overall_score})>"
        )
