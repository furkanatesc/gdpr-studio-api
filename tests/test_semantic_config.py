"""Semantik ayar varsayılanları — env-gating kapalı başlamalı."""

from app.config import Settings
from app.semantic_config import DEFAULT_SEMANTIC_MODEL, SEMANTIC_DIM


def test_semantic_kapali_baslar():
    s = Settings()
    assert s.semantic_fallback_enabled is False


def test_semantic_varsayilan_model_ve_esik():
    s = Settings()
    assert s.semantic_model == DEFAULT_SEMANTIC_MODEL
    assert s.semantic_threshold == 0.80


def test_dim_pozitif_ve_model_e5():
    assert SEMANTIC_DIM > 0
    assert "e5" in DEFAULT_SEMANTIC_MODEL.lower()
