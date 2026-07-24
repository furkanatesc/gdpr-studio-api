"""İstek başına PG RLS bağlamı: SET LOCAL app.current_org_id (Postgres'te)."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_session
from .identity import Identity, get_current_identity


def set_org_context(session: Session, org_id) -> None:
    """app.current_org_id'yi (transaction-local) kurar; sqlite'ta no-op.

    set_config(..., true) COMMIT'te sifirlanir: bir istek icinde commit'ten SONRA
    RLS'li tabloya dokunan her adim bunu YENIDEN cagirmak zorundadir. Akis
    ureticilerinde (rezervasyon commit'i → mahsuplasma/saklama) tipik tuzak.
    """
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT set_config('app.current_org_id', :oid, true)"),
            {"oid": str(org_id)},
        )


def tenant_session(
    session: Session = Depends(get_session),
    identity: Identity = Depends(get_current_identity),
) -> Session:
    set_org_context(session, identity.org_id)
    return session


def begin_provisioning(session: Session) -> None:
    """Provisioning (org-ötesi) bağlamı: app.bypass_rls=on (Postgres'te, transaction-local).

    bootstrap/accept gibi içsel olarak çok-kiracılı okuma yapan uçlar (üyelik-var-mı,
    bekleyen-davet-by-email) bunu transaction başında set eder; set_config(..., true)
    transaction-local olduğu için tek commit'te sıfırlanır → tüm RLS-tablo erişimi
    commit'ten ÖNCE bitirilmelidir. sqlite'ta no-op (app-level org_id filtreleri yeterli).
    """
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        session.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))


def end_provisioning(session: Session) -> None:
    """Bypass-RLS bağlamını kapat (app.bypass_rls='off', transaction-local).

    Kimlik çözümü gibi YALNIZ kısa bir org-ötesi okuma için bypass açıp hemen
    kapatmak gerektiğinde kullanılır; böylece aynı transaction'daki sonraki tenant
    erişimleri (app.current_org_id ile) izole kalır. sqlite'ta no-op.
    """
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        session.execute(text("SELECT set_config('app.bypass_rls', 'off', true)"))
