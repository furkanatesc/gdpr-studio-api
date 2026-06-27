"""Billing repository'leri — subscriptions / usage_counters / stripe_events."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
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
    def __init__(self, session: Session) -> None:
        self._s = session

    def _row(self, org_id: uuid.UUID, period: str) -> UsageCounter | None:
        return self._s.scalar(
            select(UsageCounter).where(
                UsageCounter.org_id == org_id, UsageCounter.period == period
            )
        )

    def get_count(self, org_id: uuid.UUID, period: str) -> int:
        row = self._row(org_id, period)
        return row.doc_count if row else 0

    def increment(self, org_id: uuid.UUID, period: str) -> int:
        row = self._row(org_id, period)
        if row is None:
            row = UsageCounter(org_id=org_id, period=period, doc_count=0)
            self._s.add(row)
        row.doc_count += 1
        self._s.flush()
        return row.doc_count


class StripeEventRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def seen(self, event_id: str) -> bool:
        return self._s.get(StripeEvent, event_id) is not None

    def record(self, event_id: str, type: str) -> None:
        self._s.add(StripeEvent(event_id=event_id, type=type))
        self._s.flush()
