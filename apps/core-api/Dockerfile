# =========================
# BUILDER STAGE
# =========================
FROM python:3.11-slim AS builder

WORKDIR /app
ENV PYTHONPATH=/app

# Install Poetry
RUN pip install --no-cache-dir poetry==1.8.3

# Copy dependency files
COPY apps/core-api/pyproject.toml apps/core-api/poetry.lock* ./apps/core-api/
COPY libs/observability /app/libs/observability


# Install dependencies
WORKDIR /app/apps/core-api
RUN poetry export --without-hashes --format=requirements.txt --with main --output requirements.txt \
 && pip install --no-cache-dir --default-timeout=1000 --retries=10 --target=/deps -r requirements.txt

# =========================
# RUNTIME STAGE
# =========================
FROM python:3.11-slim

# Create user
RUN useradd --create-home --shell /bin/bash appuser
ENV PATH="/usr/local/bin:$PATH"
WORKDIR /app

# Copy installed dependencies
COPY --from=builder /deps /usr/local/lib/python3.11/site-packages
COPY --from=builder /app/libs/observability /app/libs/observability

# Copy app code
COPY apps/core-api/src/ ./src/
COPY apps/core-api/alembic/ ./alembic/
COPY apps/core-api/alembic.ini ./
COPY apps/core-api/scripts/ ./scripts/

# Switch user
USER appuser

# Expose port
EXPOSE 8000

# Healthcheck (correct)
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD \
    python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Start server (correct)
CMD ["sh", "-c", "python -m alembic upgrade head && python -m uvicorn src.main:app --host 0.0.0.0 --port 8000"]