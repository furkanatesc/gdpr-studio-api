"""measures tablosu (global standart tedbirler)

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # measures GLOBAL referans verisidir (categories gibi) → org_id ve RLS YOK.
    op.create_table(
        "measures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tedbir", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("measures")
