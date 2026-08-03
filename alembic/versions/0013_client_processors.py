"""client_processors tablosu + RLS

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RLS = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid"
)


def upgrade() -> None:
    op.create_table(
        "client_processors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ad", sa.String(255), nullable=False),
        sa.Column("unvan", sa.String(255), nullable=False),
        sa.Column("adres", sa.Text(), nullable=True),
        sa.Column("yetkili_kisi", sa.String(255), nullable=True),
        sa.Column("iletisim", sa.String(255), nullable=True),
        sa.Column("vergi_dairesi_no", sa.String(255), nullable=True),
        sa.Column("yurt_disi", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("alt_isleyen_var", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("aktarim_aliases", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("notlar", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_client_processors_org_client", "client_processors", ["org_id", "client_id"])
    op.execute("ALTER TABLE client_processors ENABLE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY client_processors_isolation ON client_processors USING ({_RLS}) WITH CHECK ({_RLS})")
    op.execute("ALTER TABLE client_processors FORCE ROW LEVEL SECURITY")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON client_processors TO kvkk_app")


def downgrade() -> None:
    op.execute("ALTER TABLE client_processors NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS client_processors_isolation ON client_processors")
    op.execute("ALTER TABLE client_processors DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_client_processors_org_client", table_name="client_processors")
    op.drop_table("client_processors")
