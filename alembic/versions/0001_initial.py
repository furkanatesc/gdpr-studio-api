"""initial — categories + business_rules

Revision ID: 0001
Revises:
Create Date: 2026-06-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.UniqueConstraint("name", name="uq_categories_name"),
    )
    op.create_table(
        "business_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dokuman_turu", sa.String(length=50), nullable=False),
        sa.Column("kural_metni", sa.Text(), nullable=False),
    )
    op.create_index("ix_business_rules_turu", "business_rules", ["dokuman_turu"])


def downgrade() -> None:
    op.drop_index("ix_business_rules_turu", table_name="business_rules")
    op.drop_table("business_rules")
    op.drop_table("categories")
