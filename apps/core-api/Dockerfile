# Multi-stage build per docs/architecture/07-devops-cicd-deployment-scalability.md §17.3.
# Minimizes final image size/attack surface — build tools never ship in the runtime image.
#
# NOTE: build context must be the monorepo ROOT (not apps/core-api), since this
# service depends on the editable local package libs/observability. Invoked as:
#   docker build -f apps/core-api/Dockerfile .
# (docker-compose.yml sets `context: .` + `dockerfile: apps/core-api/Dockerfile`
# accordingly — see infra/docker-compose.yml.)

FROM python:3.12-slim AS builder
WORKDIR /app
RUN pip install --no-cache-dir poetry==1.8.3
COPY apps/core-api/pyproject.toml apps/core-api/poetry.lock* ./apps/core-api/
COPY libs/observability /libs/observability
WORKDIR /app/apps/core-api
RUN poetry export -f requirements.txt --output requirements.txt --without-hashes \
    && pip install --no-cache-dir --target=/deps -r requirements.txt

FROM python:3.12-slim AS runtime
RUN useradd --create-home --shell /bin/bash appuser
WORKDIR /app
COPY --from=builder /deps /usr/local/lib/python3.12/site-packages
COPY --from=builder /libs/observability /libs/observability
COPY apps/core-api/src/ ./src/
COPY apps/core-api/alembic/ ./alembic/
COPY apps/core-api/alembic.ini ./
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
