# Multi-stage build per Document 7 §17.3. Build context must be the monorepo
# ROOT (editable libs/observability dependency), invoked as:
#   docker build -f apps/ai-service/Dockerfile .

FROM python:3.12-slim AS builder
WORKDIR /app
RUN pip install --no-cache-dir poetry==1.8.3
COPY apps/ai-service/pyproject.toml apps/ai-service/poetry.lock* ./apps/ai-service/
COPY libs/observability /libs/observability
WORKDIR /app/apps/ai-service
RUN poetry export -f requirements.txt --output requirements.txt --without-hashes \
    && pip install --no-cache-dir --target=/deps -r requirements.txt

FROM python:3.12-slim AS runtime
RUN useradd --create-home --shell /bin/bash appuser
WORKDIR /app
COPY --from=builder /deps /usr/local/lib/python3.12/site-packages
COPY --from=builder /libs/observability /libs/observability
COPY apps/ai-service/src/ ./src/
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
