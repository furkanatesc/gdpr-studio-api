"""Embedder — e5 prefiks mantığı (fake) + opsiyonel gerçek model (skip-gated)."""

import os
from types import SimpleNamespace

import pytest

import app.semantic as semantic
from app.semantic import Embedder, get_embedder, to_vector_literal
from app.semantic_config import SEMANTIC_DIM


class _FakeFastembed:
    """fastembed.TextEmbedding yerine geçen sahte: aldığı metinleri kaydeder."""

    def __init__(self):
        self.seen: list[str] = []

    def embed(self, texts):
        for t in texts:
            self.seen.append(t)
            # deterministik sahte vektör (boyut önemli değil bu testte)
            yield [float(len(t))]


def test_embed_query_query_prefiksi_ekler():
    fake = _FakeFastembed()
    emb = Embedder.__new__(Embedder)  # __init__'i atla (model indirme yok)
    emb._model = fake
    emb.embed_query("konum verisi")
    assert fake.seen == ["query: konum verisi"]


def test_embed_passages_passage_prefiksi_ekler():
    fake = _FakeFastembed()
    emb = Embedder.__new__(Embedder)
    emb._model = fake
    emb.embed_passages(["Kimlik: ad, soyad", "İletişim: e-posta"])
    assert fake.seen == ["passage: Kimlik: ad, soyad", "passage: İletişim: e-posta"]


def test_to_vector_literal_format():
    assert to_vector_literal([1.0, 0.0, 2.5]) == "[1.0,0.0,2.5]"


def test_get_embedder_singleton_tek_kez_kurar(monkeypatch):
    # Model indirilmesin: Embedder ctor'unu say + sahteyle değiştir.
    monkeypatch.setattr(semantic, "_embedder", None)
    calls: list[str] = []

    def _fake_ctor(model_name):
        calls.append(model_name)
        return object()

    monkeypatch.setattr(semantic, "Embedder", _fake_ctor)
    settings = SimpleNamespace(semantic_model="m")
    first = get_embedder(settings)
    second = get_embedder(settings)
    assert first is second  # aynı örnek (singleton)
    assert calls == ["m"]  # yalnız bir kez kuruldu (kilitli çift-kontrol)


@pytest.mark.skipif(
    os.environ.get("RUN_SEMANTIC_INTEGRATION") != "1",
    reason="Gerçek model indirir; yalnız RUN_SEMANTIC_INTEGRATION=1 ile koşar",
)
def test_gercek_model_boyutu_dim_ile_eslesir():
    from app.config import Settings

    emb = get_embedder(Settings())
    vec = emb.embed_query("sağlık verisi")
    assert len(vec) == SEMANTIC_DIM
