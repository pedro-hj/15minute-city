from typing import Optional, Dict, Any
from sqlalchemy import BigInteger, Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry
from geoalchemy2.shape import to_shape
import shapely.geometry

from fifteen_minute_city.db.base import Base


class Service(Base):
    """
    Represents a physical establishment mapped from OpenStreetMap (e.g., a school, hospital).
    
    Provides metric auditability by displaying real urban services on the map.
    """

    __tablename__ = "service"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="Unique primary key identifier for the service"
    )
    execution_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("execution.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Foreign key referencing the execution",
    )
    category_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("service_category.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Foreign key referencing the service category",
    )
    representative_node_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("node.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Foreign key to the nearest network node used for Dijkstra pathfinding",
    )
    name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Name of the establishment from OpenStreetMap"
    )
    geom = mapped_column(
        Geometry("POINT", srid=4326),
        nullable=False,
        comment="Exact geographic point coordinates of the establishment (EPSG:4326)",
    )

    # Relationships
    execution: Mapped["Execution"] = relationship("Execution", back_populates="services")
    category: Mapped["ServiceCategory"] = relationship("ServiceCategory", back_populates="services")
    representative_node: Mapped["Node"] = relationship(
        "Node", back_populates="representative_services"
    )
    closest_for_reachabilities: Mapped[list["NodeReachability"]] = relationship(
        "NodeReachability", back_populates="closest_service"
    )

    @property
    def point(self) -> shapely.geometry.Point:
        """Convert WKBElement geometry to a Shapely Point."""
        return to_shape(self.geom)

    @property
    def lat(self) -> float:
        """Latitude coordinate of the service establishment."""
        return self.point.y

    @property
    def lon(self) -> float:
        """Longitude coordinate of the service establishment."""
        return self.point.x

    @property
    def geojson(self) -> Dict[str, Any]:
        """Convert spatial WKBElement point geometry into a JSON-serializable GeoJSON dict."""
        return shapely.geometry.mapping(self.point)

    def to_dict(self) -> Dict[str, Any]:
        """Convert Service model instance into a JSON-serializable dictionary."""
        return {
            "id": self.id,
            "execution_id": self.execution_id,
            "category_id": self.category_id,
            "representative_node_id": self.representative_node_id,
            "name": self.name,
            "lat": self.lat,
            "lon": self.lon,
            "geom": self.geojson,
        }

    def __repr__(self) -> str:
        return f"<Service(id={self.id}, name='{self.name}', category_id={self.category_id})>"
