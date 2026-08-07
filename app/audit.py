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
