"""client_document_versions tablosu + RLS (yayinlanmis, degismez surumler)

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RLS = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid"
)


def upgrade() -> None:
    op.create_table(
        "client_document_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("score_completeness", sa.Float(), nullable=True),
        sa.Column("score_compliance", sa.Float(), nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("published_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["document_id"], ["client_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["published_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("document_id", "version", name="uq_client_document_versions_key"),
    )
    op.create_index(
        "ix_client_document_versions_document", "client_document_versions", ["document_id"]
    )
    op.execute("ALTER TABLE client_document_versions ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY client_document_versions_isolation ON client_document_versions "
        f"USING ({_RLS}) WITH CHECK ({_RLS})"
    )
    op.execute("ALTER TABLE client_document_versions FORCE ROW LEVEL SECURITY")
    op.execute("GRANT SELECT, INSERT ON client_document_versions TO kvkk_app")
    # 0003'teki ALTER DEFAULT PRIVILEGES owner'in olusturdugu her yeni tabloya
    # UPDATE/DELETE de grant'lar; surumler DEGISMEZ olmali → bu tabloda acikca geri al.
    op.execute("REVOKE UPDATE, DELETE ON client_document_versions FROM kvkk_app")


def downgrade() -> None:
    op.execute("ALTER TABLE client_document_versions NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS client_document_versions_isolation ON client_document_versions")
    op.execute("ALTER TABLE client_document_versions DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_client_document_versions_document", table_name="client_document_versions")
    op.drop_table("client_document_versions")
