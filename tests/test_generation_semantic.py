"""_build_grounding — env-gating: flag kapalı→matcher yok, açık→matcher var."""

from types import SimpleNamespace

from app.modules import generation


class _DummySession:
    pass


def _settings(enabled):
    return SimpleNamespace(semantic_fallback_enabled=enabled, semantic_threshold=0.8, semantic_model="m")


def test_flag_kapali_matcher_yok():
    g = generation._build_grounding(_DummySession(), _settings(False))
    assert g._matcher is None


def test_flag_acik_matcher_var(monkeypatch):
    # get_embedder'ı sahteyle değiştir → gerçek model indirilmesin.
    monkeypatch.setattr(generation, "get_embedder", lambda s: object())
    g = generation._build_grounding(_DummySession(), _settings(True))
    from app.semantic import PostgresSemanticMatcher

    assert isinstance(g._matcher, PostgresSemanticMatcher)
