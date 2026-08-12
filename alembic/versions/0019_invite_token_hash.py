"""invite token'ı hash'li sakla (B5)

Revision ID: 0019
Revises: 0018
"""
from __future__ import annotations

import hashlib
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("invitations", sa.Column("token_hash", sa.String(length=64), nullable=True))
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, token FROM invitations")).fetchall()
    for row in rows:
        h = hashlib.sha256(row.token.encode("utf-8")).hexdigest()
        conn.execute(
            sa.text("UPDATE invitations SET token_hash = :h WHERE id = :id"),
            {"h": h, "id": row.id},
        )
    op.alter_column("invitations", "token_hash", nullable=False)
    op.create_index("ix_invitations_token_hash", "invitations", ["token_hash"], unique=True)
    op.drop_column("invitations", "token")


def downgrade() -> None:
    op.add_column("invitations", sa.Column("token", sa.String(length=512), nullable=True))
    op.drop_index("ix_invitations_token_hash", table_name="invitations")
    op.drop_column("invitations", "token_hash")
