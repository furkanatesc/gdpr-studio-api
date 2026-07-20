"""Postgres-tabanlı repository implementasyonları (legal_core arayüzleri)."""

from __future__ import annotations

import unicodedata
import uuid
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from legal_core.models import ProcessRecord

from .models import (
    BusinessRule,
    Category,
    Client,
    ComplianceRequirement,
    ComplianceStatus,
    GeneratedDocument,
    Invitation,
    Measure,
    Membership,
    Organization,
    Process,
    User,
)


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


class PostgresProcessRepository:
    """legal_core.ProcessRepository — süreç şablonlarını Postgres'ten sunar (global veri)."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def by_sector_and_group(self, sector: str, kisi_grubu: str | None) -> list[ProcessRecord]:
        stmt = select(Process).where(
            Process.sector == sector, Process.org_id.is_(None), Process.client_id.is_(None)
        )
        if kisi_grubu is not None:
            stmt = stmt.where(Process.kisi_grubu == kisi_grubu)
        stmt = stmt.order_by(Process.departman, Process.is_sureci, Process.alt_surec)
        rows = self._s.scalars(stmt)
        return [self._to_record(r) for r in rows]

    def client_processes(self, client_id: uuid.UUID) -> list[ProcessRecord]:
        rows = self._s.scalars(
            select(Process).where(Process.client_id == client_id)
            .order_by(Process.departman, Process.is_sureci, Process.alt_surec)
        )
        return [self._to_record(r) for r in rows]

    def replace_client(self, org_id: uuid.UUID, client_id: uuid.UUID, rows: list[dict]) -> int:
        self._s.execute(delete(Process).where(Process.client_id == client_id))
        objs = [Process(sector=r["sector"], kisi_grubu=r["kisi_grubu"], departman=r["departman"],
                        is_sureci=r["is_sureci"], alt_surec=r["alt_surec"], data=r["data"],
                        org_id=org_id, client_id=client_id) for r in rows]
        self._s.add_all(objs)
        self._s.flush()
        return len(objs)

    def person_groups(self, sector: str) -> list[str]:
        rows = self._s.scalars(
            select(Process.kisi_grubu).where(Process.sector == sector).distinct()
        )
        # Codepoint sıralaması Türkçe harfleri (Ç, Ş, İ ...) yanlış sıraya koyar
        # (ör. 'Z' < 'Ç'); NFKD anahtarı temel harfe göre sıralar (Ç → C + ¸).
        return sorted(set(rows), key=lambda s: unicodedata.normalize("NFKD", s))

    @staticmethod
    def _to_record(row: Process) -> ProcessRecord:
        d = row.data or {}
        return ProcessRecord(
            departman=row.departman, is_sureci=row.is_sureci,
            alt_surec=row.alt_surec, kisi_grubu=row.kisi_grubu,
            kategoriler=list(d.get("kategoriler", [])),
            veri_turleri=list(d.get("veri_turleri", [])),
            amaclar=list(d.get("amaclar", [])),
            hukuki_sebepler=list(d.get("hukuki_sebepler", [])),
            dayanaklar=list(d.get("dayanaklar", [])),
            saklama_sureleri=list(d.get("saklama_sureleri", [])),
            islem=list(d.get("islem", [])),
            ortam_format=list(d.get("ortam_format", [])),
            konum=list(d.get("konum", [])),
            idari_tedbirler=list(d.get("idari_tedbirler", [])),
            teknik_tedbirler=list(d.get("teknik_tedbirler", [])),
        )


class PostgresMeasureRepository:
    """legal_core.MeasureRepository — global tedbirleri Postgres'ten sunar."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def all_measures(self) -> list[str]:
        return list(self._s.scalars(select(Measure.tedbir).order_by(Measure.id)))


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


class MembershipRepository:
    """Kurum üyeleri: listele / rol değiştir / çıkar. Tüm sorgular RLS altında org'a kapalı.

    `memberships` FORCE RLS ile org'a filtrelenir → org_id koşulu savunma-derinliği + sqlite'ta
    (RLS yok) gerçek izolasyon sağlar. `users`'ta RLS yok ama join yalnız bu org'un üyelik
    satırlarından geçtiği için çapraz-kiracı sızıntı olmaz.
    """

    def __init__(self, session: Session) -> None:
        self._s = session

    def list_members(self, org_id: uuid.UUID) -> list[tuple[Membership, User]]:
        rows = self._s.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.org_id == org_id)
            .order_by(Membership.created_at)
        ).all()
        return [(m, u) for m, u in rows]

    def get_member(self, org_id: uuid.UUID, user_id: uuid.UUID) -> Membership | None:
        return self._s.scalar(
            select(Membership).where(
                Membership.org_id == org_id, Membership.user_id == user_id
            )
        )

    def count_role(self, org_id: uuid.UUID, role: str) -> int:
        return len(
            list(
                self._s.scalars(
                    select(Membership.id).where(
                        Membership.org_id == org_id, Membership.role == role
                    )
                )
            )
        )

    def set_role(self, membership: Membership, role: str) -> Membership:
        membership.role = role
        self._s.flush()
        return membership

    def remove(self, membership: Membership) -> None:
        self._s.delete(membership)
        self._s.flush()


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


class ComplianceRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def all_requirements(self) -> list[ComplianceRequirement]:
        return list(
            self._s.scalars(select(ComplianceRequirement).order_by(ComplianceRequirement.sort_order))
        )

    def statuses_for_org(self, org_id: uuid.UUID) -> dict[str, ComplianceStatus]:
        rows = self._s.scalars(select(ComplianceStatus).where(ComplianceStatus.org_id == org_id))
        return {r.requirement_key: r for r in rows}

    def upsert_status(self, org_id, key, status, source, note, updated_by) -> ComplianceStatus:
        row = self._s.scalar(
            select(ComplianceStatus).where(
                ComplianceStatus.org_id == org_id, ComplianceStatus.requirement_key == key
            )
        )
        if row is None:
            row = ComplianceStatus(org_id=org_id, requirement_key=key)
            self._s.add(row)
        row.status, row.source, row.note, row.updated_by = status, source, note, updated_by
        self._s.flush()
        return row


class GeneratedDocumentRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def record(self, org_id: uuid.UUID, doc_type: str) -> GeneratedDocument:
        row = GeneratedDocument(org_id=org_id, doc_type=doc_type)
        self._s.add(row)
        self._s.flush()
        return row

    def doc_types_for_org(self, org_id: uuid.UUID) -> set[str]:
        rows = self._s.scalars(
            select(GeneratedDocument.doc_type).where(GeneratedDocument.org_id == org_id)
        )
        return set(rows)


class ClientRepository:
    _FIELDS = ("name", "sector", "legal_name", "mersis", "vergi_dairesi", "vergi_no", "kep", "adres", "eposta", "telefon")

    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, org_id: uuid.UUID, name: str, sector: str | None = None) -> Client:
        c = Client(org_id=org_id, name=name, sector=sector)
        self._s.add(c)
        self._s.flush()
        return c

    def list(self, org_id: uuid.UUID) -> list[Client]:
        return list(self._s.scalars(select(Client).where(Client.org_id == org_id).order_by(Client.created_at)))

    def get(self, org_id: uuid.UUID, client_id: uuid.UUID) -> Client | None:
        return self._s.scalar(select(Client).where(Client.org_id == org_id, Client.id == client_id))

    def update_profile(self, org_id: uuid.UUID, client_id: uuid.UUID, **fields) -> Client | None:
        c = self.get(org_id, client_id)
        if c is None:
            return None
        for k, v in fields.items():
            if k in self._FIELDS:
                setattr(c, k, v)
        self._s.flush()
        return c
