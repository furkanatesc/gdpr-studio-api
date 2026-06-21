"""Postgres-tabanlı repository implementasyonları (legal_core arayüzleri)."""

from __future__ import annotations

import unicodedata
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import BusinessRule, Category, Invitation, Membership, Organization, User


class PostgresCategoryRepository:
    """legal_core.CategoryRepository — kategorileri Postgres'ten sunar."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def all_categories(self) -> dict[str, dict]:
        rows = self._session.execute(select(Category.name, Category.data)).all()
        return {unicodedata.normalize("NFC", name): data for name, data in rows}


class PostgresBusinessRuleRepository:
    """legal_core.BusinessRuleRepository — türe özel + 'Tümü' kuralları döndürür."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def business_rules(self, doc_type: str) -> list[str]:
        stmt = select(BusinessRule.kural_metni).where(
            BusinessRule.dokuman_turu.in_(["Tümü", doc_type])
        )
        return [r[0] for r in self._session.execute(stmt).all()]


class AccountRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get_user_by_supabase_id(self, sub: str) -> User | None:
        return self._s.scalar(select(User).where(User.supabase_user_id == sub))

    def create_user(self, sub: str, email: str) -> User:
        user = User(supabase_user_id=sub, email=email)
        self._s.add(user)
        self._s.flush()
        return user

    def get_membership_for_user(self, user_id: uuid.UUID) -> Membership | None:
        return self._s.scalar(select(Membership).where(Membership.user_id == user_id))

    def create_org_with_admin(self, name: str, user_id: uuid.UUID) -> Organization:
        org = Organization(name=name)
        self._s.add(org)
        self._s.flush()
        self._s.add(Membership(user_id=user_id, org_id=org.id, role="yonetici"))
        self._s.flush()
        return org

    def add_membership(self, user_id: uuid.UUID, org_id: uuid.UUID, role: str) -> Membership:
        m = Membership(user_id=user_id, org_id=org_id, role=role)
        self._s.add(m)
        self._s.flush()
        return m


class InvitationRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, org_id, email, role, token, expires_at: datetime, invited_by) -> Invitation:
        inv = Invitation(
            org_id=org_id, email=email, role=role, token=token,
            expires_at=expires_at, invited_by=invited_by,
        )
        self._s.add(inv)
        self._s.flush()
        return inv

    def get_by_token(self, token: str) -> Invitation | None:
        return self._s.scalar(select(Invitation).where(Invitation.token == token))

    def list_pending(self, org_id) -> list[Invitation]:
        return list(
            self._s.scalars(
                select(Invitation).where(Invitation.org_id == org_id, Invitation.status == "pending")
            )
        )

    def get_pending_by_email(self, email: str) -> Invitation | None:
        return self._s.scalar(
            select(Invitation).where(Invitation.email == email, Invitation.status == "pending")
        )

    def mark_accepted(self, inv: Invitation) -> None:
        inv.status = "accepted"
        self._s.flush()

    def revoke(self, inv_id, org_id) -> bool:
        inv = self._s.scalar(
            select(Invitation).where(Invitation.id == inv_id, Invitation.org_id == org_id)
        )
        if inv is None or inv.status != "pending":
            return False
        inv.status = "revoked"
        self._s.flush()
        return True
