import itertools
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PACKAGE_DIR = ROOT / "src" / "fifteen_minute_city"

PATH_OSM_MAPS = PACKAGE_DIR / "core/outputs"
OSM_SERVICE_TAGS: dict[str, list[str]] = {
    "amenity": ["bus_station", "school", "fuel", "bank", "hospital", "pharmacy"],
    "shop": ["supermarket"],
}
SUPPORTED_SERVICES = list(itertools.chain.from_iterable(OSM_SERVICE_TAGS.values()))

SERVICE_CATEGORIES: dict[str, list[tuple[str, str]]] = {
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
