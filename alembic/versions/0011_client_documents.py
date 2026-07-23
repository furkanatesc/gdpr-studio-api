"""client_documents tablosu + RLS

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# org_id NOT NULL (global satir yok) -> tek politika: bypass VEYA org eslesmesi.
_RLS = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid"
)


def upgrade() -> None:
    op.create_table(
        "client_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("doc_type", sa.String(20), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("score_completeness", sa.Float(), nullable=True),
        sa.Column("score_compliance", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint(
            "doc_type IN ('aydinlatma', 'cerez', 'kayit', 'dpa', 'dpia', 'ihlal')",
            name="ck_client_documents_type",
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("org_id", "client_id", "doc_type", "title", name="uq_client_documents_key"),
    )
    op.create_index("ix_client_documents_org_client", "client_documents", ["org_id", "client_id"])

    op.execute("ALTER TABLE client_documents ENABLE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY client_documents_isolation ON client_documents USING ({_RLS}) WITH CHECK ({_RLS})")
    op.execute("ALTER TABLE client_documents FORCE ROW LEVEL SECURITY")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON client_documents TO kvkk_app")


def downgrade() -> None:
    op.execute("ALTER TABLE client_documents NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS client_documents_isolation ON client_documents")
    op.execute("ALTER TABLE client_documents DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_client_documents_org_client", table_name="client_documents")
    op.drop_table("client_documents")
