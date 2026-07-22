from typing import Optional, List, Dict
from sqlalchemy import select
from sqlalchemy.orm import Session

from fifteen_minute_city.db.models.category import ServiceCategory, CategoryOsmTag

DEFAULT_CATEGORIES_DATA = [
    {
        "code": "bus_station",
        "display_name": "Bus Station",
        "moreno_pillar": "living",
        "osm_tags": [("amenity", "bus_station"), ("highway", "bus_stop")],
    },
    {
        "code": "school",
        "display_name": "School",
        "moreno_pillar": "education",
        "osm_tags": [("amenity", "school"), ("amenity", "kindergarten")],
    },
    {
        "code": "fuel",
        "display_name": "Fuel Station",
        "moreno_pillar": "living",
        "osm_tags": [("amenity", "fuel")],
    },
    {
        "code": "bank",
        "display_name": "Bank / Financial Service",
        "moreno_pillar": "commerce",
        "osm_tags": [("amenity", "bank"), ("amenity", "atm")],
    },
    {
        "code": "hospital",
        "display_name": "Hospital / Healthcare Center",
        "moreno_pillar": "health",
        "osm_tags": [("amenity", "hospital"), ("amenity", "clinic")],
    },
    {
        "code": "pharmacy",
        "display_name": "Pharmacy",
        "moreno_pillar": "health",
        "osm_tags": [("amenity", "pharmacy")],
    },
    {
        "code": "supermarket",
        "display_name": "Supermarket / Grocery",
        "moreno_pillar": "commerce",
        "osm_tags": [("shop", "supermarket"), ("shop", "convenience")],
    },
]


def list_categories(db: Session) -> List[ServiceCategory]:
    """Retrieve all service categories registered in the system."""
    return list(db.scalars(select(ServiceCategory).order_by(ServiceCategory.id)).all())


def get_category_by_code(db: Session, code: str) -> Optional[ServiceCategory]:
    """Retrieve a ServiceCategory by its unique code string."""
    return db.scalar(select(ServiceCategory).where(ServiceCategory.code == code))


def seed_default_categories(db: Session) -> List[ServiceCategory]:
    """
    Seed standard 15-minute city service categories and OSM tag mappings into the database.

    :param db: SQLAlchemy Session.
    :return: List of seeded ServiceCategory instances.
    """
    seeded_categories = []
    for data in DEFAULT_CATEGORIES_DATA:
        category = get_category_by_code(db, data["code"])
        if not category:
            category = ServiceCategory(
                code=data["code"],
                display_name=data["display_name"],
                moreno_pillar=data["moreno_pillar"],
            )
            db.add(category)
            db.flush()  # Flush to populate category.id

            for key, val in data["osm_tags"]:
                tag_mapping = CategoryOsmTag(
                    category_id=category.id,
                    osm_key=key,
                    osm_value=val,
                )
                db.add(tag_mapping)

        seeded_categories.append(category)

    db.commit()
    return seeded_categories
