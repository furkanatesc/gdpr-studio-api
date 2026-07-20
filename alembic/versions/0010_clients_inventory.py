"""clients tablosu + processes org_id/client_id + RLS

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RLS_READ = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR org_id IS NULL "
    "OR org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid"
)
_RLS_WRITE = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid"
)


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("sector", sa.String(50), nullable=True),
        sa.Column("legal_name", sa.String(255), nullable=True),
        sa.Column("mersis", sa.String(50), nullable=True),
        sa.Column("vergi_dairesi", sa.String(120), nullable=True),
        sa.Column("vergi_no", sa.String(50), nullable=True),
        sa.Column("kep", sa.String(255), nullable=True),
        sa.Column("adres", sa.Text(), nullable=True),
        sa.Column("eposta", sa.String(320), nullable=True),
        sa.Column("telefon", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_clients_org", "clients", ["org_id"])

    op.add_column("processes", sa.Column("org_id", sa.Uuid(), nullable=True))
    op.add_column("processes", sa.Column("client_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_processes_org", "processes", "organizations", ["org_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_processes_client", "processes", "clients", ["client_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_processes_org", "processes", ["org_id"])
    op.create_index("ix_processes_client", "processes", ["client_id"])
    op.drop_constraint("uq_processes_identity", "processes", type_="unique")
    op.create_unique_constraint(
        "uq_processes_identity", "processes",
        ["client_id", "sector", "departman", "is_sureci", "alt_surec", "kisi_grubu"],
    )

    for tbl in ("clients", "processes"):
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY clients_isolation ON clients USING ({_RLS_READ}) WITH CHECK ({_RLS_WRITE})")
    op.execute(f"CREATE POLICY processes_read ON processes FOR SELECT USING ({_RLS_READ})")
    op.execute(f"CREATE POLICY processes_modify ON processes FOR ALL USING ({_RLS_WRITE}) WITH CHECK ({_RLS_WRITE})")
    for tbl in ("clients", "processes"):
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON clients TO kvkk_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON processes TO kvkk_app")


def downgrade() -> None:
    for tbl in ("clients", "processes"):
        op.execute(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS processes_modify ON processes")
    op.execute("DROP POLICY IF EXISTS processes_read ON processes")
    op.execute("DROP POLICY IF EXISTS clients_isolation ON clients")
    for tbl in ("clients", "processes"):
        op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY")
    op.drop_constraint("uq_processes_identity", "processes", type_="unique")
    op.create_unique_constraint(
        "uq_processes_identity", "processes",
        ["sector", "departman", "is_sureci", "alt_surec", "kisi_grubu"],
    )
    op.drop_index("ix_processes_client", table_name="processes")
    op.drop_index("ix_processes_org", table_name="processes")
    op.drop_constraint("fk_processes_client", "processes", type_="foreignkey")
    op.drop_constraint("fk_processes_org", "processes", type_="foreignkey")
    op.drop_column("processes", "client_id")
    op.drop_column("processes", "org_id")
    op.drop_index("ix_clients_org", table_name="clients")
    op.drop_table("clients")
