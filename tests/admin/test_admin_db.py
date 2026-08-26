"""admin_session() istek-başına sessionmaker'ı yeniden kurmamalı — engine gibi
factory da cache'lenir (minor takip ticket'i, db.py)."""

from __future__ import annotations

from sqlalchemy import create_engine

import admin_api.db as db_module


def test_admin_session_reuses_cached_sessionmaker(monkeypatch):
    db_module._session_factory = None
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    monkeypatch.setattr(db_module, "get_admin_engine", lambda: engine)

    calls = {"n": 0}
    real = db_module.sessionmaker

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(db_module, "sessionmaker", counting)

    for _ in range(3):
        gen = db_module.admin_session()
        next(gen)
        gen.close()

    # 3 istek, tek factory kurulumu (engine gibi cache'li).
    assert calls["n"] == 1

    db_module._session_factory = None
