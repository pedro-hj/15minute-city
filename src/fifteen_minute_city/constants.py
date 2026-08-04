from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PACKAGE_DIR = ROOT / "src" / "fifteen_minute_city"

PATH_OSM_MAPS = PACKAGE_DIR / "core/outputs"
PATH_PBF_PATH = PACKAGE_DIR / "core/pbfs"