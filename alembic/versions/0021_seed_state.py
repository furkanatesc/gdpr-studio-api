"""seed_state: grounding seed içerik-hash'i (idempotent no-op seed)

Revision ID: 0021
Revises: 0020

Global operasyonel metadata (tenant'a bağlı DEĞİL) → RLS YOK. Tek mantıksal satır
(key='grounding'): son uygulanan seed girdilerinin SHA-256'sı. Her boot'ta destructive
DELETE+INSERT yerine hash değişmediyse seed atlanır (churn/yarış önlenir).
"""
import sqlalchemy as sa

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "seed_state",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("seed_state")
