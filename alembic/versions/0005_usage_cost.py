"""usage_counters maliyet sütunları (managed guardrail)

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # usage_counters zaten FORCE RLS (0004); yeni sütunlar aynı satırda → RLS değişmez.
    op.add_column("usage_counters", sa.Column("cost_micros", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("usage_counters", sa.Column("input_tokens", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("usage_counters", sa.Column("output_tokens", sa.BigInteger(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("usage_counters", "output_tokens")
    op.drop_column("usage_counters", "input_tokens")
    op.drop_column("usage_counters", "cost_micros")
