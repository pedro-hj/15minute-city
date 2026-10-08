"""Background worker for on-demand analyses.

Run exactly one instance as a dedicated systemd service, after migrations.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import geopandas as gpd
from sqlalchemy import select

from fifteen_minute_city.api.analysis_service import request_session_factory
from fifteen_minute_city.core.modules.locales import Region
from fifteen_minute_city.db.models.analysis_request import AnalysisRequest
from fifteen_minute_city.db.models.city import City

logger = logging.getLogger(__name__)


def _boundary_path(ibge_code: str, cache_dir: Path) -> Path:
    destination = cache_dir / "boundaries" / f"{ibge_code}.geojson"
    if destination.is_file():
        return destination

    url = (
        "https://servicodados.ibge.gov.br/api/v3/malhas/municipios/"
        f"{ibge_code}?formato=application/vnd.geo%2Bjson&qualidade=maxima"
    )
    try:
        with urlopen(Request(url, headers={"Accept": "application/vnd.geo+json"}), timeout=30) as response:
            content = response.read(20_000_001)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("Failed to fetch IBGE municipal boundary") from exc

    if len(content) > 20_000_000:
        raise RuntimeError("IBGE municipal boundary is too large")
    try:
        data = json.loads(content)
        if data.get("type") != "FeatureCollection" or not data.get("features"):
            raise ValueError("Unexpected IBGE boundary format")
    except (ValueError, AttributeError) as exc:
        raise RuntimeError("Invalid IBGE boundary response") from exc

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{ibge_code}.{os.getpid()}.geojson")
    try:
        temporary.write_bytes(content)
        # Validate before publishing into the immutable per-municipality cache.
        polygon = gpd.read_file(temporary)
        if polygon.empty or polygon.crs is None:
            raise ValueError("Invalid municipal boundary")
        if not polygon.geometry.geom_type.isin(["Polygon", "MultiPolygon"]).all():
            raise ValueError("Municipal boundary must be polygonal")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def _claim() -> dict | None:
    with request_session_factory().begin() as db:
        job = db.scalar(
            select(AnalysisRequest)
            .where(AnalysisRequest.status == "queued")
            .order_by(AnalysisRequest.requested_at, AnalysisRequest.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return None
        job.status = "processing"
        job.started_at = datetime.now(timezone.utc)
        db.flush()
        return {
            "id": job.id,
            "ibge_code": job.ibge_code,
            "city": job.city_name,
            "state": job.state_name,
        }


def _finish(job_id: str, *, city_id: int | None, error: str | None) -> None:
    with request_session_factory().begin() as db:
        job = db.get(AnalysisRequest, job_id)
        if job is None:
            return
        job.status = "error" if error else "completed"
        job.result_city_id = city_id
        job.finished_at = datetime.now(timezone.utc)
        job.error_message = error[:512] if error else None


def _process(job: dict, input_dir: Path, cache_dir: Path) -> int:
    """Persist new results using the existing Region pipeline."""
    with request_session_factory()() as db:
        city = db.scalar(select(City).where(City.ibge_code == job["ibge_code"]))
        if city is not None and any(
            execution.status == "completed" for execution in city.executions
        ):
            return city.id

    boundary = _boundary_path(job["ibge_code"], cache_dir)
    region = Region(
        {"city": job["city"], "state": job["state"], "country": "Brazil"},
        pbf_path=input_dir / "brazil-latest.osm.pbf",
        cache_dir=cache_dir,
        boundary_path=boundary,
        enable_db=True,
        ibge_code=job["ibge_code"],
    )
    region.build_graph()
    region.locate_services()
    region.load_population_grid(
        None,
        population_column="TOTAL",
        id_column="ID_UNICO",
    )
    region.calculate_accessibility()

    with request_session_factory()() as db:
        city = db.scalar(select(City).where(City.ibge_code == job["ibge_code"]))
        if city is None:
            raise RuntimeError("Analysis finished without a persisted city")
        return city.id


def main() -> None:
    """Start only one worker. systemd should restart this process on failure."""
    logging.basicConfig(level=logging.INFO)
    input_dir = Path(os.getenv("ANALYSES_INPUT_DIR", "data/input"))
    cache_dir = Path(os.getenv("ANALYSES_CACHE_DIR", "data/cache"))
    if not (input_dir / "brazil-latest.osm.pbf").is_file():
        raise FileNotFoundError("Missing brazil-latest.osm.pbf")
    if not list(input_dir.glob("grade_id*.zip")):
        raise FileNotFoundError("Missing grade_id*.zip population tiles")

    # The service must be a singleton. Reclaim previously interrupted tasks.
    with request_session_factory().begin() as db:
        interrupted = db.scalars(
            select(AnalysisRequest).where(AnalysisRequest.status == "processing")
        ).all()
        for job in interrupted:
            job.status = "queued"
            job.started_at = None
    logger.info("Analysis worker started; recovered %d interrupted jobs", len(interrupted))

    while True:
        job = _claim()
        if job is None:
            time.sleep(10)
            continue
        logger.info("Processing IBGE municipality %s", job["ibge_code"])
        try:
            city_id = _process(job, input_dir, cache_dir)
        except Exception:
            logger.exception("Public analysis %s failed", job["id"])
            _finish(job["id"], city_id=None, error="Analysis failed; contact the administrator")
        else:
            _finish(job["id"], city_id=city_id, error=None)


if __name__ == "__main__":
    main()
