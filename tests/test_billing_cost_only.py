import uuid

from app.billing.quota import record_cost_only
from app.config import get_settings


class _Repo:
    def __init__(self):
        self.increment_called = False
        self.cost_added = None

    def increment(self, *a, **k):
        self.increment_called = True

    def add_cost(self, org_id, period, it, ot, cm):
        self.cost_added = (it, ot, cm)


def test_record_cost_only_does_not_increment_doc_counter(monkeypatch):
    import app.billing.quota as q
    repo = _Repo()
    monkeypatch.setattr(q, "UsageRepository", lambda s: repo)
    monkeypatch.setattr(q, "set_org_context", lambda s, o: None)
    monkeypatch.setattr(q, "cost_micros", lambda m, it, ot: 123)
    session = type("S", (), {"commit": lambda self: None})()
    record_cost_only(session, get_settings(), uuid.uuid4(),
                     model="claude-sonnet-4-6", input_tokens=10, output_tokens=20, byok=False)
    assert repo.increment_called is False
    assert repo.cost_added == (10, 20, 123)


def test_record_cost_only_byok_noop(monkeypatch):
    import app.billing.quota as q
    repo = _Repo()
    monkeypatch.setattr(q, "UsageRepository", lambda s: repo)
    monkeypatch.setattr(q, "set_org_context", lambda s, o: None)
    session = type("S", (), {"commit": lambda self: None})()
    record_cost_only(session, get_settings(), uuid.uuid4(),
                     model="claude-sonnet-4-6", input_tokens=10, output_tokens=20, byok=True)
    assert repo.cost_added is None
    assert repo.increment_called is False
