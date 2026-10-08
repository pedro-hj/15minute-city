import os

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fifteen_minute_city.api.analysis_routes import router as analysis_router
from fifteen_minute_city.api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(
        title="15-Minute City API",
        summary="Urban accessibility results and public analysis requests.",
        description=(
            "Consult completed analyses by city, origin strategy, service "
            "category and metric. Authenticate with the X-API-Key header."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    cors_origins = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["X-API-Key", "Content-Type"],
        )

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(router)
    app.include_router(analysis_router)
    return app


app = create_app()


def run() -> None:
    uvicorn.run(
        "fifteen_minute_city.api.app:app",
        host=os.getenv("API_HOST", "127.0.0.1"),
        port=int(os.getenv("API_PORT", "8000")),
        proxy_headers=True,
        forwarded_allow_ips=os.getenv("API_TRUSTED_PROXY_IPS", "127.0.0.1"),
    )
