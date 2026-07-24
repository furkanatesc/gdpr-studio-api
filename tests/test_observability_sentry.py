"""I6: Sentry frame local'leri kapali olmali — akis hatasinda muvekkil envanteri (records) ve
uretilmis tam belge (full_text) capture_exception'a frame local'i olarak sizmamali."""

from __future__ import annotations

from app.observability import init_sentry


def test_init_sentry_kapatir_frame_local_degiskenlerini(monkeypatch):
    captured = {}

    def _fake_init(**kwargs):
        captured.update(kwargs)

    import sentry_sdk

    monkeypatch.setattr(sentry_sdk, "init", _fake_init)

    ok = init_sentry("https://fake@sentry.example/1", "production")

    assert ok is True
    assert captured.get("include_local_variables") is False


def test_init_sentry_dsn_bossa_noop(monkeypatch):
    import sentry_sdk

    called = {"n": 0}

    def _fake_init(**kwargs):
        called["n"] += 1

    monkeypatch.setattr(sentry_sdk, "init", _fake_init)

    ok = init_sentry("", "production")

    assert ok is False
    assert called["n"] == 0
