# Base Image with Python 3.12 (Debian Bookworm)
FROM python:3.12-slim-bookworm

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONPATH=/app/src \
    PATH="/app/.venv/bin:$PATH"

# Install native system dependencies: osmium-tool, C++ build tools, and GDAL/GEOS libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    osmium-tool \
    build-essential \
    libgdal-dev \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager from official image
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /uvx /bin/

WORKDIR /app

# Install project dependencies first (for optimal Docker layer caching)
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-install-project --no-cache

# Copy project source code
COPY . .

# Install the project itself
RUN uv sync --frozen --no-cache

# Accept the same explicit CLI parameters used outside the container.
ENTRYPOINT ["fifteen-minute-city"]
CMD ["--help"]
