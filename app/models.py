"""SQLAlchemy modelleri — grounding referans verisi.

Faz 1'de kategoriler ve iş kuralları GLOBAL referans verisidir (tenant'a bağlı değil);
tenant'a özel envanter Faz 2'de eklenir. Kategori kaydı esnek yapısı korunarak JSONB
tutulur (categories.json ile birebir). Şema vektöre-hazırdır: embedding sütunu Faz 2'de
pgvector ile eklenecek bir migration'dır.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

# Postgres'te JSONB (prod); SQLite'ta (test) generic JSON'a düşer. Şema/davranış aynı kalır.
_JSON = JSONB().with_variant(JSON(), "sqlite")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # NFC normalize edilmiş kategori adı (grounding anahtarı).
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    # veri_turu, amaclar, hukuki_sebepler, kisi_grubu, saklama_sureleri, *_tedbirler
    data: Mapped[dict] = mapped_column(_JSON, nullable=False, default=dict)


class BusinessRule(Base):
    __tablename__ = "business_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 'Tümü' (genel) veya doküman türü: aydinlatma/cerez/kayit/dpa/dpia/ihlal
    dokuman_turu: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    kural_metni: Mapped[str] = mapped_column(Text, nullable=False)


Index("ix_business_rules_turu", BusinessRule.dokuman_turu)


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'deleting', 'suspended')", name="ck_organizations_status"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Süreç şablonu seçimi için (grounding ekseni). None → süreç grounding'i devre dışı,
    # kategori fallback'i çalışır. Kapalı liste: app.sectors.SECTORS.
    sector: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # DSAR (H3-2): soft-delete. 'deleting' → erişim fail-closed; deleted_at + 14 gün = purge (Part 2).
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Client(Base):
    """Müvekkil — hukuk bürosunun (org) hizmet verdiği şirket. Sektör/envanter/veri sorumlusu buraya bağlı."""

    __tablename__ = "clients"
    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(50), nullable=True)
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mersis: Mapped[str | None] = mapped_column(String(50), nullable=True)
    vergi_dairesi: Mapped[str | None] = mapped_column(String(120), nullable=True)
    vergi_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    kep: Mapped[str | None] = mapped_column(String(255), nullable=True)
    adres: Mapped[str | None] = mapped_column(Text, nullable=True)
    eposta: Mapped[str | None] = mapped_column(String(320), nullable=True)
    telefon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _uuid_pk()
    supabase_user_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        CheckConstraint("role IN ('yonetici', 'avukat')", name="ck_memberships_role"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    # MVP: tek kullanıcı = tek kurum → user_id unique
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # yonetici | avukat
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Invitation(Base):
    __tablename__ = "invitations"
    __table_args__ = (
        CheckConstraint("role IN ('yonetici', 'avukat')", name="ck_invitations_role"),
        CheckConstraint("status IN ('pending', 'accepted', 'revoked')", name="ck_invitations_status"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    invited_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint("plan IN ('baslangic', 'standart', 'premium')", name="ck_subscriptions_plan"),
        CheckConstraint("interval IN ('month', 'year')", name="ck_subscriptions_interval"),
        CheckConstraint("status IN ('active', 'past_due', 'canceled')", name="ck_subscriptions_status"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), unique=True, nullable=False, index=True
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    plan: Mapped[str] = mapped_column(String(20), nullable=False, default="baslangic")
    interval: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UsageCounter(Base):
    __tablename__ = "usage_counters"
    __table_args__ = (
        UniqueConstraint("org_id", "period", name="uq_usage_org_period"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    period: Mapped[str] = mapped_column(String(7), nullable=False)  # 'YYYY-MM'
    doc_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")


class StripeEvent(Base):
    __tablename__ = "stripe_events"
    event_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ComplianceRequirement(Base):
    __tablename__ = "compliance_requirements"
    __table_args__ = (
        CheckConstraint("source_type IN ('manual', 'auto')", name="ck_compliance_req_source_type"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    madde_ref: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    group: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    source_type: Mapped[str] = mapped_column(String(10), nullable=False, default="manual")
    auto_signal: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ComplianceStatus(Base):
    __tablename__ = "compliance_status"
    __table_args__ = (
        UniqueConstraint("org_id", "requirement_key", name="uq_compliance_status_org_key"),
        CheckConstraint("status IN ('yapildi', 'eksik', 'uygulanmaz')", name="ck_compliance_status_status"),
        CheckConstraint("source IN ('user', 'auto_suggested')", name="ck_compliance_status_source"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    requirement_key: Mapped[str] = mapped_column(String(100), nullable=False)
    # nullable: not (kanıt/gerekçe) statü seçilmeden kaydedilebilir → null statü skora sayılmaz
    # (satır-yok ile aynı). CHECK 'status IN (...)' NULL'ı geçirir (bilinmeyen = false değil).
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GeneratedDocument(Base):
    __tablename__ = "generated_documents"
    __table_args__ = (
        CheckConstraint(
            "doc_type IN ('aydinlatma', 'cerez', 'kayit', 'dpa', 'dpia', 'ihlal')",
            name="ck_generated_documents_type",
        ),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    doc_type: Mapped[str] = mapped_column(String(20), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClientDocument(Base):
    __tablename__ = "client_documents"
    __table_args__ = (
        CheckConstraint(
            "doc_type IN ('aydinlatma', 'cerez', 'kayit', 'dpa', 'dpia', 'ihlal')",
            name="ck_client_documents_type",
        ),
        UniqueConstraint("org_id", "client_id", "doc_type", "title", name="uq_client_documents_key"),
        Index("ix_client_documents_org_client", "org_id", "client_id"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    doc_type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    score_completeness: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_compliance: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ClientDocumentVersion(Base):
    __tablename__ = "client_document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version", name="uq_client_document_versions_key"),
        Index("ix_client_document_versions_document", "document_id"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("client_documents.id", ondelete="CASCADE"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    score_completeness: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_compliance: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClientProcessor(Base):
    """Müvekkilin (veri sorumlusu) bir veri işleyeni — DPA üretimi için kalıcı kimlik + aktarım eşlemesi."""

    __tablename__ = "client_processors"
    __table_args__ = (
        Index("ix_client_processors_org_client", "org_id", "client_id"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    ad: Mapped[str] = mapped_column(String(255), nullable=False)
    unvan: Mapped[str] = mapped_column(String(255), nullable=False)
    adres: Mapped[str | None] = mapped_column(Text, nullable=True)
    yetkili_kisi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    iletisim: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vergi_dairesi_no: Mapped[str | None] = mapped_column(String(255), nullable=True)
    yurt_disi: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    alt_isleyen_var: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    aktarim_aliases: Mapped[list] = mapped_column(_JSON, nullable=False, default=list)
    notlar: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Process(Base):
    """Global süreç şablonu (VERBİS satırı). Faz 1'de org_id YOK — referans verisi.

    Sorgu eksenleri (sector, kisi_grubu) gerçek sütun; kalan 20 alan JSONB (Category deseni).
    Faz 2'de aynı şemaya org_id + RLS eklenerek müşteri envanterine dönüşecek.
    """

    __tablename__ = "processes"
    __table_args__ = (
        UniqueConstraint(
            "client_id", "sector", "departman", "is_sureci", "alt_surec", "kisi_grubu",
            name="uq_processes_identity",
        ),
        Index("ix_processes_sector_group", "sector", "kisi_grubu"),
        Index("ix_processes_client", "client_id"),
        Index("ix_processes_org", "org_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sector: Mapped[str] = mapped_column(String(50), nullable=False)
    kisi_grubu: Mapped[str] = mapped_column(String(150), nullable=False)
    departman: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    is_sureci: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    alt_surec: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True
    )
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=True
    )
    data: Mapped[dict] = mapped_column(_JSON, nullable=False, default=dict)


class Measure(Base):
    """Global standart güvenlik tedbiri (KVKK m.12). Kategoriye bağlı değil — org geneli.

    Faz 1 processes/categories gibi GLOBAL referans verisi (org_id YOK).
    """

    __tablename__ = "measures"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tedbir: Mapped[str] = mapped_column(Text, nullable=False)


class AuditLog(Base):
    """Append-only denetim izi (KVKK m.12). UPDATE/DELETE RLS+REVOKE ile reddedilir.
    Veri minimizasyonu: içerik/e-posta yazılmaz; meta küçük PII-olmayan bağlam."""

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_org_created", "org_id", "created_at"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    # ondelete CASCADE: migration 0014 ile birebir (DSAR purge org-satırı silince audit gider;
    # append-only REVOKE'u FK-aksiyonu bypass eder). Model↔migration paritesi.
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meta: Mapped[dict | None] = mapped_column(_JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
