"""Pytest configuration — sets required environment variables before any
test module imports src.config, so the test suite is self-contained and
does not depend on a developer having created a local .env file (which is
gitignored and won't exist in CI).

This must run before `from src.main import app` (or anything importing
src.config) in any test module, which is why it lives in conftest.py —
pytest guarantees conftest.py is loaded before test collection.
"""

from __future__ import annotations

import os

os.environ.setdefault("ENVIRONMENT", "ci")
os.environ.setdefault("LOG_LEVEL", "INFO")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test"
)
os.environ.setdefault("REDIS_CACHE_URL", "redis://localhost:6379/0")
os.environ.setdefault("REDIS_BROKER_URL", "redis://localhost:6380/0")
os.environ.setdefault("REDIS_SESSION_URL", "redis://localhost:6381/0")
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production-use-only-in-ci")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test-internal-token-not-for-production-use-in-ci")
