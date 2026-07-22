from typing import Optional, Dict, Any
from sqlalchemy import BigInteger, Integer, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry
from geoalchemy2.shape import to_shape
import shapely.geometry

from fifteen_minute_city.db.base import Base


class Node(Base):
    """
    Represents a pedestrian network graph node (street intersection) for an execution.
    
    Serves as the spatial granular unit for reachability index calculations and map visualization.
    """

    __tablename__ = "node"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="Unique primary key identifier for the node"
    )
    execution_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("execution.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Foreign key referencing the specific execution",
    )
    osm_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True, comment="Original OpenStreetMap node ID for data provenance"
    )
    geom = mapped_column(
        Geometry("POINT", srid=4326),
        nullable=False,
        comment="Geographic point coordinates of the node (EPSG:4326)",
    )
    overall_index: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Denormalized overall reachability index for fast map rendering"
    )
    overall_mean_time: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Denormalized average travel time in minutes across all categories"
    )

    # Relationships
    execution: Mapped["Execution"] = relationship("Execution", back_populates="nodes")
    representative_services: Mapped[list["Service"]] = relationship(
        "Service", back_populates="representative_node"
    )
    reachabilities: Mapped[list["NodeReachability"]] = relationship(
        "NodeReachability", back_populates="node", cascade="all, delete-orphan"
    )

    @property
    def point(self) -> shapely.geometry.Point:
        """Convert WKBElement geometry to a Shapely Point."""
        return to_shape(self.geom)

    @property
    def lat(self) -> float:
        """Latitude coordinate of the node."""
        return self.point.y

    @property
    def lon(self) -> float:
        """Longitude coordinate of the node."""
        return self.point.x

    @property
    def geojson(self) -> Dict[str, Any]:
        """Convert spatial WKBElement point geometry into a JSON-serializable GeoJSON dict."""
        return shapely.geometry.mapping(self.point)

    def to_dict(self) -> Dict[str, Any]:
        """Convert Node model instance into a JSON-serializable dictionary."""
        return {
            "id": self.id,
            "execution_id": self.execution_id,
            "osm_id": self.osm_id,
            "lat": self.lat,
            "lon": self.lon,
            "geom": self.geojson,
            "overall_index": self.overall_index,
            "overall_mean_time": self.overall_mean_time,
        }

    def __repr__(self) -> str:
        return f"<Node(id={self.id}, osm_id={self.osm_id}, execution_id={self.execution_id})>"
