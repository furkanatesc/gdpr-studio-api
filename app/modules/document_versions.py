"""Belge sürümleme — taslağı değişmez bir sürüme yayınlar (tür-bağımsız)."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from ..auth.tenant_session import set_org_context
from ..models import ClientDocument, ClientDocumentVersion
from ..repositories import ClientDocumentVersionRepository


def publish_document(
    session, org_id: uuid.UUID, client_id: uuid.UUID, document_id: uuid.UUID,
    note: str | None, published_by: uuid.UUID,
) -> ClientDocumentVersion | None:
    set_org_context(session, org_id)
    draft = session.scalar(
        select(ClientDocument).where(
            ClientDocument.org_id == org_id,
            ClientDocument.client_id == client_id,
            ClientDocument.id == document_id,
        )
    )
    if draft is None:
        return None
    ver = ClientDocumentVersionRepository(session).publish(
        org_id, document_id, draft.content, draft.score_completeness,
        draft.score_compliance, note, published_by,
    )
    session.commit()
    return ver
