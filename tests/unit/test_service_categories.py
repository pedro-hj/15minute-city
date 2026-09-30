from fifteen_minute_city.constants import SERVICE_CATEGORIES


def test_expected_categories() -> None:
    assert SERVICE_CATEGORIES == {
        "health": [
            ("amenity", "hospital"),
            ("amenity", "clinic"),
            ("amenity", "doctors"),
            ("amenity", "pharmacy"),
            ("healthcare", "hospital"),
            ("healthcare", "clinic"),
        ],
        "education": [
            ("amenity", "kindergarten"),
            ("amenity", "school"),
        ],
        "food": [
            ("shop", "supermarket"),
            ("shop", "convenience"),
            ("shop", "bakery"),
            ("shop", "greengrocer"),
            ("shop", "butcher"),
            ("shop", "seafood"),
            ("shop", "deli"),
            ("amenity", "marketplace"),
        ],
        "culture": [
            ("amenity", "library"),
            ("amenity", "cinema"),
            ("tourism", "museum"),
        ],
    }
