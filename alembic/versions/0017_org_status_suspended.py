"""org status suspended (H3-3 retention)

Revision ID: 0017
Revises: 0016
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAME = "ck_organizations_status"


def upgrade() -> None:
    op.drop_constraint(_NAME, "organizations", type_="check")
    op.create_check_constraint(_NAME, "organizations",
                               "status IN ('active', 'deleting', 'suspended')")


def downgrade() -> None:
    op.drop_constraint(_NAME, "organizations", type_="check")
    op.create_check_constraint(_NAME, "organizations",
                               "status IN ('active', 'deleting')")
