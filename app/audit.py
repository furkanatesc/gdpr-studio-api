"""Denetim izi kayıt servisi (KVKK m.12). Eylemin transaction'ında, commit'ten ÖNCE."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from .models import AuditLog
from .observability import get_client_ip, get_request_id


def record_audit(session: Session, *, org_id: uuid.UUID, action: str,
                 actor_user_id: uuid.UUID | None = None, target_type: str | None = None,
                 target_id: str | None = None, meta: dict | None = None) -> None:
    session.add(AuditLog(
        org_id=org_id, actor_user_id=actor_user_id, action=action,
        target_type=target_type, target_id=target_id,
        ip=get_client_ip(), request_id=get_request_id(), meta=meta,
    ))


def record_generated_document(session: Session, org_id: uuid.UUID, doc_type: str,
                               user_id: uuid.UUID | None = None) -> uuid.UUID:
    """Başarılı üretimi generated_documents'a yazar + document.generated denetim olayı üretir."""
    from .repositories import GeneratedDocumentRepository

    doc_id = GeneratedDocumentRepository(session).record(org_id, doc_type, user_id)
    record_audit(
        session, org_id=org_id, action="document.generated",
        actor_user_id=user_id, target_type="document", target_id=doc_type,
    )
    return doc_id
