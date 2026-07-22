"""Unit tests for the redaction module — Document 5 §14.1's security-critical
guarantee (no secret ever reaches a log line) deserves real test coverage,
not just implementation."""

from __future__ import annotations

from observability.redaction import redact, redaction_processor


def test_redacts_top_level_password_field() -> None:
    result = redact({"username": "alice", "password": "s3cret"})
    assert result == {"username": "alice", "password": "[REDACTED]"}


def test_redacts_case_insensitively() -> None:
    result = redact({"Authorization": "Bearer xyz"})
    assert result == {"Authorization": "[REDACTED]"}


def test_redacts_nested_dicts() -> None:
    result = redact({"user": {"email": "a@b.com", "hashed_password": "abc"}})
    assert result == {"user": {"email": "a@b.com", "hashed_password": "[REDACTED]"}}


def test_redacts_within_lists() -> None:
    result = redact([{"token": "t1"}, {"token": "t2"}])
    assert result == [{"token": "[REDACTED]"}, {"token": "[REDACTED]"}]


def test_leaves_non_sensitive_data_untouched() -> None:
    data = {"portfolioId": "abc-123", "quantity": 10}
    assert redact(data) == data


def test_redaction_processor_matches_structlog_processor_signature() -> None:
    event_dict = {"event": "login", "password": "hunter2"}
    result = redaction_processor(None, "info", event_dict)
    assert result == {"event": "login", "password": "[REDACTED]"}
