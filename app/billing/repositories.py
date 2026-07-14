"""Billing repository'leri — subscriptions / usage_counters / stripe_events."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..models import StripeEvent, Subscription, UsageCounter


class SubscriptionRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get_by_org(self, org_id: uuid.UUID) -> Subscription | None:
        return self._s.scalar(select(Subscription).where(Subscription.org_id == org_id))

    def get_by_customer(self, customer_id: str) -> Subscription | None:
        return self._s.scalar(
            select(Subscription).where(Subscription.stripe_customer_id == customer_id)
        )

    def upsert(
        self,
        org_id: uuid.UUID,
        *,
        customer_id: str | None = None,
        subscription_id: str | None = None,
        plan: str | None = None,
        interval: str | None = None,
        status: str | None = None,
        current_period_end: datetime | None = None,
    ) -> Subscription:
        sub = self.get_by_org(org_id)
        if sub is None:
            sub = Subscription(org_id=org_id)
            self._s.add(sub)
        if customer_id is not None:
            sub.stripe_customer_id = customer_id
        if subscription_id is not None:
            sub.stripe_subscription_id = subscription_id
        if plan is not None:
            sub.plan = plan
        if interval is not None:
            sub.interval = interval
        if status is not None:
            sub.status = status
        if current_period_end is not None:
            sub.current_period_end = current_period_end
        self._s.flush()
        return sub

    def set_status_by_customer(self, customer_id: str, status: str) -> bool:
        sub = self.get_by_customer(customer_id)
        if sub is None:
            return False
        sub.status = status
        self._s.flush()
        return True


class UsageRepository:
    """Aylık kullanım sayaçları. Artışlar ATOMİKTİR (tek ifade, read-modify-write yok).

    Neden: `SELECT` → Python'da `+= 1` → `UPDATE` deseni READ COMMITTED altında lost-update
    üretir (eşzamanlı iki üretim aynı N'i okur, ikisi de N+1 yazar → bir artış kaybolur;
    kota/bütçe sessizce aşılır). Bunun yerine `INSERT ... ON CONFLICT (org_id, period)
    DO UPDATE SET col = col + :delta` — çakışan yazar satır kilidinde bekler ve GÜNCEL
    değerin üstüne ekler.
    """

    def __init__(self, session: Session) -> None:
        self._s = session

    def _row(self, org_id: uuid.UUID, period: str) -> UsageCounter | None:
        return self._s.scalar(
            select(UsageCounter).where(
                UsageCounter.org_id == org_id, UsageCounter.period == period
            )
        )

    def _bump(self, org_id: uuid.UUID, period: str, **deltas: int) -> int:
        """Atomik artış; güncel doc_count'u döner. deltas: sayaç kolonu → eklenecek değer."""
        table = UsageCounter.__table__
        # Dialect'e özgü upsert: prod Postgres, testler SQLite (ikisi de ON CONFLICT destekler).
        insert = pg_insert if self._s.get_bind().dialect.name == "postgresql" else sqlite_insert
        stmt = insert(table).values(org_id=org_id, period=period, **deltas)
        stmt = stmt.on_conflict_do_update(
            index_elements=[table.c.org_id, table.c.period],
            set_={column: table.c[column] + delta for column, delta in deltas.items()},
        ).returning(table.c.doc_count)
        return self._s.execute(stmt).scalar_one()

    def get_count(self, org_id: uuid.UUID, period: str) -> int:
        row = self._row(org_id, period)
        return row.doc_count if row else 0

    def increment(self, org_id: uuid.UUID, period: str) -> int:
        return self._bump(org_id, period, doc_count=1)

    def get_cost(self, org_id: uuid.UUID, period: str) -> int:
        row = self._row(org_id, period)
        return row.cost_micros if row else 0

    def add_cost(
        self,
        org_id: uuid.UUID,
        period: str,
        input_tokens: int,
        output_tokens: int,
        cost_micros: int,
    ) -> None:
        # cost_micros negatif olabilir (akış 'done' mahsuplaşması rezervasyon farkını düşer).
        self._bump(
            org_id,
            period,
            cost_micros=cost_micros,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


class StripeEventRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def seen(self, event_id: str) -> bool:
        return self._s.get(StripeEvent, event_id) is not None

    def record(self, event_id: str, type: str) -> None:
        self._s.add(StripeEvent(event_id=event_id, type=type))
        self._s.flush()
