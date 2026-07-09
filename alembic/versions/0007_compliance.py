"""compliance — requirements + status + generated_documents (+ RLS)

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RLS_TABLES = [("compliance_status", "org_id"), ("generated_documents", "org_id")]


def upgrade() -> None:
    op.create_table(
        "compliance_requirements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(100), nullable=False, unique=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("madde_ref", sa.String(255), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("group", sa.String(100), nullable=False, server_default=""),
        sa.Column("source_type", sa.String(10), nullable=False, server_default="manual"),
        sa.Column("auto_signal", sa.String(100), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("source_type IN ('manual', 'auto')", name="ck_compliance_req_source_type"),
    )
    op.create_table(
        "compliance_status",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("requirement_key", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("source", sa.String(20), nullable=False, server_default="user"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("org_id", "requirement_key", name="uq_compliance_status_org_key"),
        sa.CheckConstraint("status IN ('yapildi', 'eksik', 'uygulanmaz')", name="ck_compliance_status_status"),
        sa.CheckConstraint("source IN ('user', 'auto_suggested')", name="ck_compliance_status_source"),
    )
    op.create_index("ix_compliance_status_org_id", "compliance_status", ["org_id"])
    op.create_table(
        "generated_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("doc_type", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "doc_type IN ('aydinlatma', 'cerez', 'kayit', 'dpa', 'dpia', 'ihlal')",
            name="ck_generated_documents_type",
        ),
    )
    op.create_index("ix_generated_documents_org_id", "generated_documents", ["org_id"])

    for tbl, col in _RLS_TABLES:
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {tbl}_isolation ON {tbl} USING ("
            f"current_setting('app.bypass_rls', true) = 'on' "
            f"OR {col} = NULLIF(current_setting('app.current_org_id', true), '')::uuid)"
        )
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    for tbl, _ in _RLS_TABLES:
        op.execute(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {tbl}_isolation ON {tbl}")
    op.drop_index("ix_generated_documents_org_id", table_name="generated_documents")
    op.drop_table("generated_documents")
    op.drop_index("ix_compliance_status_org_id", table_name="compliance_status")
    op.drop_table("compliance_status")
    op.drop_table("compliance_requirements")
