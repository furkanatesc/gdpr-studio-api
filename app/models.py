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
    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Süreç şablonu seçimi için (grounding ekseni). None → süreç grounding'i devre dışı,
    # kategori fallback'i çalışır. Kapalı liste: app.sectors.SECTORS.
    sector: Mapped[str | None] = mapped_column(String(50), nullable=True)


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
    token: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
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
    status: Mapped[str] = mapped_column(String(20), nullable=False)
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
