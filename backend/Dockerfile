# SupplyScope backend — production-style image built with uv
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /srv/backend

# Layer-cached dependency install: copy manifests first
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --no-install-project 2>/dev/null || uv sync --no-dev || true

# Application code
COPY app ./app
COPY scripts ./scripts
COPY data_generator ./data_generator

EXPOSE 8000
CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
