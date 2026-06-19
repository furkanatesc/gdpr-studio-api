"""SQLAlchemy modelleri — grounding referans verisi.

Faz 1'de kategoriler ve iş kuralları GLOBAL referans verisidir (tenant'a bağlı değil);
tenant'a özel envanter Faz 2'de eklenir. Kategori kaydı esnek yapısı korunarak JSONB
tutulur (categories.json ile birebir). Şema vektöre-hazırdır: embedding sütunu Faz 2'de
pgvector ile eklenecek bir migration'dır.
"""

from __future__ import annotations

from sqlalchemy import Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # NFC normalize edilmiş kategori adı (grounding anahtarı).
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    # veri_turu, amaclar, hukuki_sebepler, kisi_grubu, saklama_sureleri, *_tedbirler
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class BusinessRule(Base):
    __tablename__ = "business_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 'Tümü' (genel) veya doküman türü: aydinlatma/cerez/kayit/dpa/dpia/ihlal
    dokuman_turu: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    kural_metni: Mapped[str] = mapped_column(Text, nullable=False)


Index("ix_business_rules_turu", BusinessRule.dokuman_turu)
