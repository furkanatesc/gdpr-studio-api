"""SQLAlchemy modelleri — grounding referans verisi.

Faz 1'de kategoriler ve iş kuralları GLOBAL referans verisidir (tenant'a bağlı değil);
tenant'a özel envanter Faz 2'de eklenir. Kategori kaydı esnek yapısı korunarak JSONB
tutulur (categories.json ile birebir). Şema vektöre-hazırdır: embedding sütunu Faz 2'de
pgvector ile eklenecek bir migration'dır.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, func
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


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _uuid_pk()
    supabase_user_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Membership(Base):
    __tablename__ = "memberships"
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
