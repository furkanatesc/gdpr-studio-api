"""platform admin: kvkk_admin_ro role + back-office tables

Revision ID: 0020
Revises: 0019
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def _is_pg():
    return op.get_bind().dialect.name == "postgresql"


def upgrade():
    op.create_table("platform_admins",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("supabase_user_id", sa.String(), nullable=False, unique=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("confidentiality_ack_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table("platform_audit_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("actor_platform_admin_id", pg.UUID(as_uuid=True), sa.ForeignKey("platform_admins.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_email_snapshot", sa.String(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("target_org_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("target_type", sa.String(), nullable=True),
        sa.Column("target_id", sa.String(), nullable=True),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("result_row_count", sa.Integer(), nullable=True),
        sa.Column("meta", pg.JSONB(), nullable=True),
        sa.Column("prev_hash", sa.String(), nullable=True),
        sa.Column("row_hash", sa.String(), nullable=False),
        sa.Column("ip", sa.String(), nullable=True),
        sa.Column("request_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_platform_audit_actor_created", "platform_audit_logs", ["actor_platform_admin_id", "created_at"])
    op.create_index("ix_platform_audit_org_created", "platform_audit_logs", ["target_org_id", "created_at"])
    op.create_table("impersonation_sessions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("platform_admin_id", pg.UUID(as_uuid=True), sa.ForeignKey("platform_admins.id"), nullable=False),
        sa.Column("target_org_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("requires_dual_control", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("approved_by", pg.UUID(as_uuid=True), sa.ForeignKey("platform_admins.id"), nullable=True),
        sa.Column("bound_sub", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_kind", sa.String(), nullable=True),
    )
    # PREFLIGHT RULING (2026-08-17): plan's table def had no primary key, but a
    # SQLAlchemy ORM model requires one — added surrogate id BigInteger PK.
    # UniqueConstraint kept for the UPSERT (day, metric_key, dims) path.
    op.create_table("platform_metrics_daily",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("metric_key", sa.String(), nullable=False),
        sa.Column("dims", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("value_numeric", sa.Numeric(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("day", "metric_key", "dims", name="uq_platform_metrics_daily"),
    )
    op.create_index("ix_platform_metrics_key_day", "platform_metrics_daily", ["metric_key", "day"])
    # aggregate indexes the rollup job needs (currently missing)
    op.create_index("ix_org_status", "organizations", ["status"])
    op.create_index("ix_sub_plan_status", "subscriptions", ["plan", "status"])
    op.create_index("ix_gen_docs_created", "generated_documents", ["created_at"])
    op.create_index("ix_usage_period", "usage_counters", ["period"])

    if _is_pg():
        op.execute("""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='kvkk_admin_ro') THEN
            CREATE ROLE kvkk_admin_ro LOGIN PASSWORD 'kvkk_admin_ro' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='kvkk_metrics_job') THEN
            CREATE ROLE kvkk_metrics_job LOGIN PASSWORD 'kvkk_metrics_job' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
          END IF;
        END $$;""")
        op.execute("GRANT USAGE ON SCHEMA public TO kvkk_admin_ro, kvkk_metrics_job")
        op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO kvkk_admin_ro")
        op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO kvkk_metrics_job")
        op.execute("GRANT INSERT ON platform_audit_logs TO kvkk_admin_ro")
        op.execute("REVOKE UPDATE, DELETE ON platform_audit_logs FROM kvkk_admin_ro, kvkk_metrics_job")
        op.execute("GRANT INSERT ON impersonation_sessions TO kvkk_admin_ro")
        op.execute("GRANT UPDATE (ended_at, end_kind) ON impersonation_sessions TO kvkk_admin_ro")
        op.execute("GRANT INSERT, UPDATE ON platform_metrics_daily TO kvkk_metrics_job")
        op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO kvkk_admin_ro, kvkk_metrics_job")
        op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO kvkk_admin_ro")
        op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO kvkk_metrics_job")


def downgrade():
    for t in ("platform_metrics_daily", "impersonation_sessions", "platform_audit_logs", "platform_admins"):
        op.drop_table(t)
    for ix in ("ix_org_status", "ix_sub_plan_status", "ix_gen_docs_created", "ix_usage_period"):
        op.drop_index(ix)
    if _is_pg():
        op.execute(
            "DO $$ BEGIN "
            "IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'kvkk_admin_ro') THEN "
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT ON TABLES FROM kvkk_admin_ro; "
            "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM kvkk_admin_ro; "
            "REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM kvkk_admin_ro; "
            "REVOKE USAGE ON SCHEMA public FROM kvkk_admin_ro; "
            "DROP ROLE kvkk_admin_ro; "
            "END IF; "
            "IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'kvkk_metrics_job') THEN "
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT ON TABLES FROM kvkk_metrics_job; "
            "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM kvkk_metrics_job; "
            "REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM kvkk_metrics_job; "
            "REVOKE USAGE ON SCHEMA public FROM kvkk_metrics_job; "
            "DROP ROLE kvkk_metrics_job; "
            "END IF; END $$;"
        )
