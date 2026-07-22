"""Unit tests for ListLoginHistoryUseCase."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.application.auth.list_login_history_use_case import (
    ListLoginHistoryCommand,
    ListLoginHistoryUseCase,
)
from src.domain.auth.entities import LoginHistoryEntry
from src.domain.auth.value_objects import UserId
from tests.unit.application.fakes import FakeLoginHistoryRepository


class TestListLoginHistoryUseCase:
    async def test_returns_entries_for_the_given_user_only(self) -> None:
        repo = FakeLoginHistoryRepository()
        user_id = UserId.new()
        other_user_id = UserId.new()
        now = datetime.now(UTC)

        await repo.save(
            LoginHistoryEntry(
                id=UserId.new(),
                user_id=user_id,
                ip_address="127.0.0.1",
                user_agent="pytest",
                device_label="Test Runner",
                success=True,
                failure_reason=None,
                created_at=now,
            )
        )
        await repo.save(
            LoginHistoryEntry(
                id=UserId.new(),
                user_id=other_user_id,
                ip_address="127.0.0.1",
                user_agent="pytest",
                device_label="Test Runner",
                success=True,
                failure_reason=None,
                created_at=now,
            )
        )

        use_case = ListLoginHistoryUseCase(repo)
        results = await use_case.execute(ListLoginHistoryCommand(user_id))

        assert len(results) == 1
        assert results[0].user_id == user_id

    async def test_respects_the_limit_parameter(self) -> None:
        repo = FakeLoginHistoryRepository()
        user_id = UserId.new()
        now = datetime.now(UTC)
        for i in range(5):
            await repo.save(
                LoginHistoryEntry(
                    id=UserId.new(),
                    user_id=user_id,
                    ip_address="127.0.0.1",
                    user_agent="pytest",
                    device_label="Test Runner",
                    success=True,
                    failure_reason=None,
                    created_at=now + timedelta(seconds=i),
                )
            )

        use_case = ListLoginHistoryUseCase(repo)
        results = await use_case.execute(ListLoginHistoryCommand(user_id, limit=2))

        assert len(results) == 2
