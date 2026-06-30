"""Yerel embedding (fastembed/ONNX) + Postgres pgvector semantik matcher.

fastembed yalnız bu modülde import edilir (lazy): semantic_fallback_enabled
kapalıyken Embedder hiç kurulmaz, model yüklenmez. legal_core saf kalır.
"""

from __future__ import annotations

import threading

from sqlalchemy import text
from sqlalchemy.orm import Session

from .config import Settings

# e5 ailesi asimetrik prefiks ister: sorgu "query: ", belge "passage: ".
_QUERY_PREFIX = "query: "
_PASSAGE_PREFIX = "passage: "


def to_vector_literal(vec: list[float]) -> str:
    """float listesini pgvector metin literaline çevirir: '[1.0,0.0,...]'.

    repr() bilimsel gösterim üretse de (örn. 1e-05) pgvector kabul eder.
    """
    return "[" + ",".join(repr(x) for x in vec) + "]"


class Embedder:
    """fastembed TextEmbedding sarmalayıcı; e5 prefikslerini gizler."""

    def __init__(self, model_name: str) -> None:
        from fastembed import TextEmbedding  # lazy: yalnız etkinken yüklenir

        self._model = TextEmbedding(model_name)

    def embed_query(self, text: str) -> list[float]:
        vecs = self._model.embed([_QUERY_PREFIX + text])
        return [float(x) for x in next(iter(vecs))]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        out = self._model.embed([_PASSAGE_PREFIX + t for t in texts])
        return [[float(x) for x in v] for v in out]


_embedder: Embedder | None = None
_embedder_lock = threading.Lock()


def get_embedder(settings: Settings) -> Embedder:
    """Süreç-içi singleton (model bir kez yüklenir).

    Çift-kontrollü kilit: FastAPI senkron uçları threadpool'da koşar; kilit
    olmadan iki eşzamanlı cold-start isteği ~1GB e5 modelini 2× yükleyebilir.

    Deployment notu: model ilk kullanımda HF'den iner. Üretimde flag açıksa
    cold-start gecikmesini önlemek için modeli image'a göm ya da başlangıçta
    ısıt (offline `python -m app.embed_categories` zaten on-disk cache'i doldurur).
    """
    global _embedder
    if _embedder is None:
        with _embedder_lock:
            if _embedder is None:
                _embedder = Embedder(settings.semantic_model)
    return _embedder


class PostgresSemanticMatcher:
    """Etiketi pgvector cosine en-yakın kategoriye eşler; eşik-altı/hatada None.

    legal_core.SemanticMatcher protokolünü sağlar (yapısal — import bağımlılığı yok).
    """

    def __init__(self, session: Session, embedder: Embedder, threshold: float) -> None:
        self._session = session
        self._embedder = embedder
        self._threshold = threshold

    def _nearest(self, qvec: list[float]) -> tuple[str, float] | None:
        # cosine mesafe (<=>) → benzerlik = 1 - mesafe. pgvector literali '[...]'.
        lit = to_vector_literal(qvec)
        row = self._session.execute(
            text(
                """
                SELECT c.name AS name,
                       1 - (ce.embedding <=> CAST(:q AS vector)) AS score
                FROM category_embeddings ce
                JOIN categories c ON c.id = ce.category_id
                ORDER BY ce.embedding <=> CAST(:q AS vector)
                LIMIT 1
                """
            ),
            {"q": lit},
        ).first()
        if row is None:
            return None
        return (row.name, float(row.score))

    def best_category(self, tag: str) -> tuple[str, float] | None:
        try:
            qvec = self._embedder.embed_query(tag)
            hit = self._nearest(qvec)
        except Exception:
            return None  # fail-soft: semantik hata üretimi patlatmaz
        if hit is None or hit[1] < self._threshold:
            return None
        return hit
