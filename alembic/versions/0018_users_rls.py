"""users RLS — membership-EXISTS policy + FORCE (H3)

Revision ID: 0018
Revises: 0017
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY users_isolation ON users USING ("
        "current_setting('app.bypass_rls', true) = 'on' "
        "OR EXISTS (SELECT 1 FROM memberships m "
        "WHERE m.user_id = users.id "
        "AND m.org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid))"
    )
    op.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("ALTER TABLE users NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS users_isolation ON users")
    op.execute("ALTER TABLE users DISABLE ROW LEVEL SECURITY")
