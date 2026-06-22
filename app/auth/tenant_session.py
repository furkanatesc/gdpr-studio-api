"""İstek başına PG RLS bağlamı: SET LOCAL app.current_org_id (Postgres'te)."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_session
from .identity import Identity, get_current_identity


def tenant_session(
    session: Session = Depends(get_session),
    identity: Identity = Depends(get_current_identity),
) -> Session:
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT set_config('app.current_org_id', :oid, true)"),
            {"oid": str(identity.org_id)},
        )
    return session
