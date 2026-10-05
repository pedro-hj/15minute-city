from sqlalchemy import select
from sqlalchemy.orm import Session

from fifteen_minute_city.constants import SERVICE_CATEGORIES
from fifteen_minute_city.db.models.category import CategoryOsmTag, ServiceCategory

CATEGORY_METADATA = {
    "health": {"display_name": "Health", "moreno_pillar": "health"},
    "education": {"display_name": "Education", "moreno_pillar": "education"},
    "food": {"display_name": "Food", "moreno_pillar": "commerce"},
    "culture": {"display_name": "Culture", "moreno_pillar": "entertainment"},
}

DEFAULT_CATEGORIES_DATA = [
    {
        "code": code,
        "display_name": CATEGORY_METADATA[code]["display_name"],
        "moreno_pillar": CATEGORY_METADATA[code]["moreno_pillar"],
        "osm_tags": osm_tags,
    }
    for code, osm_tags in SERVICE_CATEGORIES.items()
]


def list_categories(db: Session) -> list[ServiceCategory]:
    """Retrieve all service categories registered in the system."""
    return list(db.scalars(select(ServiceCategory).order_by(ServiceCategory.id)).all())


def get_category_by_code(db: Session, code: str) -> ServiceCategory | None:
    """Retrieve a ServiceCategory by its unique code string."""
    return db.scalar(select(ServiceCategory).where(ServiceCategory.code == code))


def seed_default_categories(db: Session) -> list[ServiceCategory]:
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
        else:
            category.display_name = data["display_name"]
            category.moreno_pillar = data["moreno_pillar"]
            existing_tags = {(tag.osm_key, tag.osm_value) for tag in category.osm_tags}
            for key, val in data["osm_tags"]:
                if (key, val) not in existing_tags:
                    db.add(
                        CategoryOsmTag(
                            category_id=category.id,
                            osm_key=key,
                            osm_value=val,
                        )
                    )

        seeded_categories.append(category)

    db.commit()
    return seeded_categories
