"""processes tablosu + organizations.sector

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql   # 0001_initial.py ile AYNI desen

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # processes GLOBAL referans verisidir (categories gibi) → org_id ve RLS YOK.
    # Faz 2'de per-tenant envanter için org_id + RLS ayrı migration ile eklenecek.
    # JSONB: 0001_initial.py'deki categories.data ile birebir aynı desen (migration'lar
    # yalnız Postgres'te koşar; SQLite testleri Base.metadata.create_all kullanır).
    op.create_table(
        "processes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sector", sa.String(50), nullable=False),
        sa.Column("kisi_grubu", sa.String(150), nullable=False),
        sa.Column("departman", sa.String(150), nullable=False, server_default=""),
        sa.Column("is_sureci", sa.String(255), nullable=False, server_default=""),
        sa.Column("alt_surec", sa.String(500), nullable=False, server_default=""),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.UniqueConstraint("sector", "departman", "is_sureci", "alt_surec", "kisi_grubu",
                            name="uq_processes_identity"),
    )
    op.create_index("ix_processes_sector_group", "processes", ["sector", "kisi_grubu"])
    op.add_column("organizations", sa.Column("sector", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("organizations", "sector")
    op.drop_index("ix_processes_sector_group", table_name="processes")
    op.drop_table("processes")
