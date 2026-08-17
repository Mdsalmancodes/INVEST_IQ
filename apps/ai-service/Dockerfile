# ============================================================================
# INVEST IQ - AI SERVICE
# Dockerfile
# ============================================================================


# ============================================================================
# BUILDER STAGE
# ============================================================================

FROM python:3.11-slim AS builder

# --------------------------------------------------------------------------
# Base directory
# --------------------------------------------------------------------------

WORKDIR /app


# --------------------------------------------------------------------------
# Install Poetry
# --------------------------------------------------------------------------

RUN pip install --no-cache-dir poetry==1.8.3


# --------------------------------------------------------------------------
# Poetry / network configuration
#
# POETRY_REQUESTS_TIMEOUT controls Poetry's HTTP download timeout.
#
# This is important because the AI service has large ML dependencies
# including PyTorch and related packages.
# --------------------------------------------------------------------------

ENV POETRY_REQUESTS_TIMEOUT=1000
ENV PIP_DEFAULT_TIMEOUT=1000
ENV PIP_RETRIES=10


# --------------------------------------------------------------------------
# Copy dependency definitions
# --------------------------------------------------------------------------

COPY apps/ai-service/pyproject.toml \
     apps/ai-service/poetry.lock* \
     ./apps/ai-service/


# --------------------------------------------------------------------------
# Copy local observability library
# --------------------------------------------------------------------------

COPY libs/observability \
     /app/libs/observability


# --------------------------------------------------------------------------
# AI service directory
# --------------------------------------------------------------------------

WORKDIR /app/apps/ai-service


# --------------------------------------------------------------------------
# Install dependencies
#
# --with dev is intentional.
#
# It installs:
#
#   pytest
#   pytest-asyncio
#   mypy
#   ruff
#
# This allows us to run the complete test suite inside Docker.
# --------------------------------------------------------------------------

RUN poetry config virtualenvs.create false \
    && poetry install \
        --with dev \
        --no-root \
        --no-interaction \
        --no-ansi


# ============================================================================
# RUNTIME STAGE
# ============================================================================

FROM python:3.11-slim AS runtime


# --------------------------------------------------------------------------
# Create non-root application user
# --------------------------------------------------------------------------

RUN useradd \
        --create-home \
        --shell /bin/bash \
        appuser


# --------------------------------------------------------------------------
# Application directory
# --------------------------------------------------------------------------

WORKDIR /app


# --------------------------------------------------------------------------
# Copy installed Python packages
# --------------------------------------------------------------------------

COPY --from=builder \
     /usr/local/lib/python3.11/site-packages \
     /usr/local/lib/python3.11/site-packages


# --------------------------------------------------------------------------
# Copy observability library
# --------------------------------------------------------------------------

COPY --from=builder \
     /app/libs/observability \
     /app/libs/observability


# --------------------------------------------------------------------------
# Copy AI service source
# --------------------------------------------------------------------------

COPY apps/ai-service/src/ \
     /app/src/


# --------------------------------------------------------------------------
# Copy AI service tests
#
# IMPORTANT:
# This is required so pytest can discover the tests inside the container.
# --------------------------------------------------------------------------

COPY apps/ai-service/tests/ \
     /app/tests/


# --------------------------------------------------------------------------
# Copy pytest configuration
#
# The [tool.pytest.ini_options] section lives in pyproject.toml.
# --------------------------------------------------------------------------

COPY apps/ai-service/pyproject.toml \
     /app/pyproject.toml


# ============================================================================
# DATA / MODEL DIRECTORIES
# ============================================================================

RUN mkdir -p \
        /app/data \
        /app/data/models \
        /app/data/model_registry \
    && chown -R appuser:appuser /app/data \
    && chmod -R 775 /app/data


# ============================================================================
# PYTHON CONFIGURATION
# ============================================================================

ENV PYTHONPATH=/app


# ============================================================================
# RUN AS NON-ROOT
# ============================================================================

USER appuser


# ============================================================================
# PORT
# ============================================================================

EXPOSE 8001


# ============================================================================
# HEALTHCHECK
# ============================================================================

HEALTHCHECK \
    --interval=30s \
    --timeout=5s \
    --start-period=30s \
    --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')" \
    || exit 1


# ============================================================================
# START AI SERVICE
# ============================================================================

CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]