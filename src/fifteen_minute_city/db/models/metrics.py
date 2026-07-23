from sqlalchemy import BigInteger, Integer, Float, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fifteen_minute_city.db.base import Base


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
    travel_time_minutes: Mapped[float] = mapped_column(
        Float, nullable=False, comment="Calculated walking/travel time in minutes"
    )
    within_threshold: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="Flag indicating if travel time is within the 15-minute threshold"
    )

    # Relationships
    node: Mapped["Node"] = relationship("Node", back_populates="reachabilities")
    category: Mapped["ServiceCategory"] = relationship("ServiceCategory", back_populates="reachabilities")
    closest_service: Mapped["Service"] = relationship("Service", back_populates="closest_for_reachabilities")

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
    mean_travel_time_minutes: Mapped[float] = mapped_column(
        Float, nullable=False, comment="Average travel time in minutes for this category across all city nodes"
    )
    percentage_within_threshold: Mapped[float] = mapped_column(
        Float, nullable=False, comment="Percentage of city nodes reachable within the 15-minute threshold (0-100%)"
    )
    overall_index: Mapped[float] = mapped_column(
        Float, nullable=False, comment="Consolidated reachability score used for city ranking and analysis"
    )

    # Relationships
    execution: Mapped["Execution"] = relationship("Execution", back_populates="city_indices")
    category: Mapped["ServiceCategory"] = relationship("ServiceCategory", back_populates="city_indices")

    def __repr__(self) -> str:
        return (
            f"<CityIndex(execution_id={self.execution_id}, category_id={self.category_id}, "
            f"overall_index={self.overall_index})>"
        )
