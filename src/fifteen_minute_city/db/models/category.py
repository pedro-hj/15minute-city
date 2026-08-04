from sqlalchemy import Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fifteen_minute_city.db.base import Base


class ServiceCategory(Base):
    """
    Domain entity defining urban service categories (e.g., Health, Education).
    
    Standardizes service categories across cities based on Carlos Moreno's 15-Minute City pillars.
    """

    __tablename__ = "service_category"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="Unique primary key identifier for the category"
    )
    code: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True, comment="Stable code identifier (e.g., 'saude', 'educacao')"
    )
    display_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Human-readable category label (e.g., 'Health')"
    )
    moreno_pillar: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Associated Moreno 15-Minute City pillar (e.g., 'health', 'education')"
    )

    # Relationships
    osm_tags: Mapped[list["CategoryOsmTag"]] = relationship(
        "CategoryOsmTag", back_populates="category", cascade="all, delete-orphan"
    )
    services: Mapped[list["Service"]] = relationship(
        "Service", back_populates="category"
    )
    reachabilities: Mapped[list["NodeReachability"]] = relationship(
        "NodeReachability", back_populates="category"
    )
    city_indices: Mapped[list["CityIndex"]] = relationship(
        "CityIndex", back_populates="category"
    )

    def __repr__(self) -> str:
        return f"<ServiceCategory(id={self.id}, code='{self.code}', display_name='{self.display_name}')>"


class CategoryOsmTag(Base):
    """
    Associative model mapping service categories to OpenStreetMap key-value tags.
    
    Enables dynamic configuration of OpenStreetMap tags for each service category.
    """

    __tablename__ = "category_osm_tag"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="Unique primary key identifier for the tag mapping"
    )
    category_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("service_category.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Foreign key referencing the service category",
    )
    osm_key: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="OpenStreetMap tag key (e.g., 'amenity', 'shop')"
    )
    osm_value: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="OpenStreetMap tag value (e.g., 'hospital', 'supermarket')"
    )

    # Relationships
    category: Mapped["ServiceCategory"] = relationship("ServiceCategory", back_populates="osm_tags")

    def __repr__(self) -> str:
        return f"<CategoryOsmTag(id={self.id}, tag='{self.osm_key}={self.osm_value}')>"
