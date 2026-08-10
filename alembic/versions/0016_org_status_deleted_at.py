"""organizations.status + deleted_at (DSAR H3-2 soft-delete)

Part 1: hesap kapatma (erasure) soft-delete işaretler; status='deleting' → erişim
fail-closed. deleted_at + 14 gün = kalıcı purge (Part 2). Geri-dolgu: mevcut org'lar
status='active', deleted_at=NULL.

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
    )
    op.add_column(
        "organizations",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_organizations_status", "organizations", "status IN ('active', 'deleting')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_organizations_status", "organizations", type_="check")
    op.drop_column("organizations", "deleted_at")
    op.drop_column("organizations", "status")
