"""Domain <-> ORM mapping functions for the alerts bounded context.

Mirrors the pattern in watchlist_mappers.py — pure functions, no side
effects, isolate the domain layer from SQLAlchemy model shape. Alert has
no child entities (unlike Watchlist), so there is only one mapper pair,
matching market_data_mappers.py's single-entity style.
"""

from __future__ import annotations

from decimal import Decimal

from src.domain.alerts.entities import Alert
from src.domain.alerts.value_objects import AlertId, InstrumentId
from src.infrastructure.persistence.postgres.alert_models import AlertModel


def alert_to_domain(model: AlertModel) -> Alert:
    return Alert(
        id=AlertId(model.id),
        user_id=str(model.user_id),
        instrument_id=InstrumentId(model.instrument_id),
        condition_type=model.condition_type,  # type: ignore[arg-type]  # DB CHECK constraint guarantees a valid ConditionType
        threshold=Decimal(model.threshold),
        is_recurring=model.is_recurring,
        cooldown_minutes=model.cooldown_minutes,
        is_active=model.is_active,
        triggered_at=model.triggered_at,
        created_at=model.created_at,
    )


def alert_to_model(alert: Alert, existing: AlertModel | None) -> AlertModel:
    model = existing if existing is not None else AlertModel(id=alert.id.value)
    model.user_id = alert.user_id  # type: ignore[assignment]  # str -> UUID column, driver-coerced
    model.instrument_id = alert.instrument_id.value
    model.condition_type = alert.condition_type
    model.threshold = alert.threshold  # type: ignore[assignment]  # Decimal -> Numeric column
    model.is_recurring = alert.is_recurring
    model.cooldown_minutes = alert.cooldown_minutes
    model.is_active = alert.is_active
    model.triggered_at = alert.triggered_at
    model.created_at = alert.created_at
    return model
