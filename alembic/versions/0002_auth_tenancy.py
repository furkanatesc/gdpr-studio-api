"""auth_tenancy — organizations + users + memberships + invitations + RLS

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("supabase_user_id", sa.String(255), nullable=False, unique=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('yonetici', 'avukat')", name="ck_memberships_role"),
    )
    op.create_index("ix_memberships_org_id", "memberships", ["org_id"])
    op.create_table(
        "invitations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("token", sa.String(512), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invited_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('yonetici', 'avukat')", name="ck_invitations_role"),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'revoked')", name="ck_invitations_status"),
    )
    op.create_index("ix_invitations_org_id", "invitations", ["org_id"])

    # --- RLS (savunma derinliği) ---
    for tbl, col in [("organizations", "id"), ("memberships", "org_id"), ("invitations", "org_id")]:
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {tbl}_isolation ON {tbl} USING "
            f"({col} = current_setting('app.current_org_id', true)::uuid)"
        )


def downgrade() -> None:
    for tbl in ["invitations", "memberships", "organizations"]:
        op.execute(f"DROP POLICY IF EXISTS {tbl}_isolation ON {tbl}")

    op.drop_index("ix_invitations_org_id", table_name="invitations")
    op.drop_table("invitations")
    op.drop_index("ix_memberships_org_id", table_name="memberships")
    op.drop_table("memberships")
    op.drop_table("users")
    op.drop_table("organizations")
