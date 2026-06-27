"""Entitlement çözümü: org'un planı + aylık kullanım → kota kararı."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from .repositories import SubscriptionRepository, UsageRepository

FREE_MONTHLY_QUOTA = 5

# Kota yalnızca bu iç durumlarda sıfırlanır (Stripe trialing → dahili "active"'e eşlenir).
ENTITLED_STATUSES = frozenset({"active", "trialing"})


def current_period(now: datetime | None = None) -> str:
    """Takvim ayı anahtarı 'YYYY-MM' (UTC). Yeni ay = yeni anahtar → cron'suz reset."""
    now = now or datetime.now(UTC)
    return now.strftime("%Y-%m")


@dataclass(frozen=True)
class Entitlement:
    plan: str
    status: str
    interval: str | None
    current_period_end: datetime | None
    quota: int | None  # None => sınırsız
    used: int


def resolve_entitlement(session: Session, org_id: uuid.UUID) -> Entitlement:
    sub = SubscriptionRepository(session).get_by_org(org_id)
    used = UsageRepository(session).get_count(org_id, current_period())
    if sub is None or sub.plan == "baslangic":
        return Entitlement(
            plan="baslangic",
            status=sub.status if sub else "active",
            interval=None,
            current_period_end=sub.current_period_end if sub else None,
            quota=FREE_MONTHLY_QUOTA,
            used=used,
        )
    # Kota, durum bilgisine bağlıdır: yalnızca aktif/deneme abonelikleri sınırsız erişim alır.
    # Plan ve durum ise frontend'in kart-hata uyarısı göstermesi için gerçek değerleriyle raporlanır.
    quota = None if sub.status in ENTITLED_STATUSES else FREE_MONTHLY_QUOTA
    return Entitlement(
        plan=sub.plan,
        status=sub.status,
        interval=sub.interval,
        current_period_end=sub.current_period_end,
        quota=quota,
        used=used,
    )
