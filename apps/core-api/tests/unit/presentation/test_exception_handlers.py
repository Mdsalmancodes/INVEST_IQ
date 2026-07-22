"""Verifies every domain exception subclass has an HTTP mapping (or is
explicitly handled as a special case) — Document 5 §14.3's own stated
requirement: "enforced by a unit test that asserts every domain exception
type has a mapping, so a forgotten mapping fails CI rather than surfacing
as an unhandled 500 in production."
"""

from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException

import src.domain.auth.exceptions as auth_exceptions
from src.domain.auth.exceptions import AccountLockedError, AuthDomainError
from src.presentation.exception_handlers import _EXCEPTION_STATUS_MAP, raise_as_http


def _all_domain_exception_classes() -> list[type[AuthDomainError]]:
    return [
        obj
        for _, obj in inspect.getmembers(auth_exceptions, inspect.isclass)
        if issubclass(obj, AuthDomainError) and obj is not AuthDomainError
    ]


class TestExceptionMappingCompleteness:
    def test_every_domain_exception_has_a_mapping_or_special_case(self) -> None:
        unmapped = [
            exc_cls
            for exc_cls in _all_domain_exception_classes()
            if exc_cls not in _EXCEPTION_STATUS_MAP and exc_cls is not AccountLockedError
        ]
        assert unmapped == [], (
            f"The following domain exceptions have no HTTP mapping registered "
            f"in src.presentation.exception_handlers: {[c.__name__ for c in unmapped]}"
        )

    @pytest.mark.parametrize("exc_cls", _all_domain_exception_classes())
    def test_raise_as_http_converts_every_exception_type(
        self, exc_cls: type[AuthDomainError]
    ) -> None:
        instance = exc_cls(30) if exc_cls is AccountLockedError else exc_cls("test message")
        with pytest.raises(HTTPException) as exc_info:
            raise_as_http(instance)
        assert 400 <= exc_info.value.status_code < 600
