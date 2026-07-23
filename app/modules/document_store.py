# app/modules/document_store.py
"""Muvekkil belgesi saklama — RLS-guvenli, doc_type-agnostik ortak helper.

Aydinlatma + cerez (ve sonraki turler) ayni yolu kullanir. Kritik: reserve/settle_generation_usage
commit'i app.current_org_id GUC'sini (transaction-local) sifirlar; bu yuzden okuma+yazimdan ONCE
org baglami burada yeniden kurulur (bkz. app/modules/clients.py:154).
"""

from __future__ import annotations

from sqlalchemy import text

from legal_core.models import ClientProfile

from ..repositories import ClientDocumentRepository, ComplianceRepository
from .compliance_logic import compliance_snapshot_score


def client_profile(client) -> ClientProfile:
    return ClientProfile(
        ad=client.name,
        unvan=client.legal_name,
        adres=client.adres,
        mersis=client.mersis,
        vergi_dairesi=client.vergi_dairesi,
        vergi_no=client.vergi_no,
        kep=client.kep,
        eposta=client.eposta,
        telefon=client.telefon,
    )


def store_client_document(
    session, org_id, client_id, doc_type, title, content, score_completeness
) -> None:
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        session.execute(text("SELECT set_config('app.current_org_id', :o, true)"), {"o": str(org_id)})
    statuses = {k: v.status for k, v in ComplianceRepository(session).statuses_for_org(org_id).items()}
    ClientDocumentRepository(session).upsert(
        org_id, client_id, doc_type, title, content,
        score_completeness=score_completeness,
        score_compliance=compliance_snapshot_score(statuses, doc_type),
    )
    session.commit()
