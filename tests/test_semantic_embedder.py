"""Embedder — e5 prefiks mantığı (fake) + opsiyonel gerçek model (skip-gated)."""

import os

import pytest

from app.semantic import Embedder, get_embedder
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


def test_embed_query_query_prefiksi_ekler(monkeypatch):
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


@pytest.mark.skipif(
    os.environ.get("RUN_SEMANTIC_INTEGRATION") != "1",
    reason="Gerçek model indirir; yalnız RUN_SEMANTIC_INTEGRATION=1 ile koşar",
)
def test_gercek_model_boyutu_dim_ile_eslesir():
    from app.config import Settings

    emb = get_embedder(Settings())
    vec = emb.embed_query("sağlık verisi")
    assert len(vec) == SEMANTIC_DIM
