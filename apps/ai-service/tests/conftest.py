"""Pytest configuration — sets required environment variables before any
test module imports src.config. Same rationale as core-api's conftest.py.
"""

from __future__ import annotations

import os

os.environ.setdefault("ENVIRONMENT", "ci")
os.environ.setdefault("LOG_LEVEL", "INFO")
os.environ.setdefault("REDIS_CACHE_URL", "redis://localhost:6379/0")
os.environ.setdefault("REDIS_BROKER_URL", "redis://localhost:6380/0")
