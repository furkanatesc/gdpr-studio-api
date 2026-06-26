"""billing — subscriptions + usage_counters + stripe_events (+ RLS)

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# org-kapsamlı tablolar → 0003 deseniyle FORCE RLS + bypass-clause policy.
_RLS_TABLES = [("subscriptions", "org_id"), ("usage_counters", "org_id")]


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False, unique=True),
        sa.Column("stripe_customer_id", sa.String(255), nullable=True, unique=True),
        sa.Column("stripe_subscription_id", sa.String(255), nullable=True, unique=True),
        sa.Column("plan", sa.String(20), nullable=False, server_default="baslangic"),
        sa.Column("interval", sa.String(10), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("plan IN ('baslangic', 'standart', 'premium')", name="ck_subscriptions_plan"),
        sa.CheckConstraint("interval IN ('month', 'year')", name="ck_subscriptions_interval"),
        sa.CheckConstraint("status IN ('active', 'past_due', 'canceled')", name="ck_subscriptions_status"),
    )
    op.create_index("ix_subscriptions_org_id", "subscriptions", ["org_id"])
    op.create_table(
        "usage_counters",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("doc_count", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("org_id", "period", name="uq_usage_org_period"),
    )
    op.create_index("ix_usage_counters_org_id", "usage_counters", ["org_id"])
    # stripe_events: org-ötesi idempotency tablosu → RLS YOK (yalnız bypass bağlamında yazılır).
    op.create_table(
        "stripe_events",
        sa.Column("event_id", sa.String(255), primary_key=True),
        sa.Column("type", sa.String(100), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- FORCE RLS (0003 deseni) ---
    for tbl, col in _RLS_TABLES:
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {tbl}_isolation ON {tbl} USING ("
            f"current_setting('app.bypass_rls', true) = 'on' "
            f"OR {col} = NULLIF(current_setting('app.current_org_id', true), '')::uuid)"
        )
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")
    # NOT: 0003'teki ALTER DEFAULT PRIVILEGES sayesinde bu tablolar kvkk_app'e otomatik grant'lanır.


def downgrade() -> None:
    for tbl, _ in _RLS_TABLES:
        op.execute(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {tbl}_isolation ON {tbl}")
    op.drop_table("stripe_events")
    op.drop_index("ix_usage_counters_org_id", table_name="usage_counters")
    op.drop_table("usage_counters")
    op.drop_index("ix_subscriptions_org_id", table_name="subscriptions")
    op.drop_table("subscriptions")
