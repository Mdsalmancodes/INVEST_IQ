"""add missing index on alerts.user_id

Revision ID: 0006_alerts_user_id_index
Revises: 0005_alerts_context
Create Date: 2026-07-26

Production audit finding: `alerts` was the only one of the three
per-user-resource tables (portfolios, watchlists, alerts) missing a plain
index on `user_id`, despite `ListAlertsUseCase`/`SqlAlchemyAlertRepository
.list_for_user()` filtering by `user_id` on every `GET /alerts` call —
`0005_alerts_context.py` only added a partial index on `instrument_id`
(idx_alerts_active_instrument), not one on user_id. Matches
`idx_watchlists_user` (0004_watchlist_context.py) and the equivalent
index already present on `portfolios.user_id`.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006_alerts_user_id_index"
down_revision: str | None = "0005_alerts_context"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.create_index("idx_alerts_user", "alerts", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_alerts_user", table_name="alerts")
