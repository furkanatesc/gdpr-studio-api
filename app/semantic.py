"""Yerel embedding (fastembed/ONNX) + Postgres pgvector semantik matcher.

fastembed yalnız bu modülde import edilir (lazy): semantic_fallback_enabled
kapalıyken Embedder hiç kurulmaz, model yüklenmez. legal_core saf kalır.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from .config import Settings

# e5 ailesi asimetrik prefiks ister: sorgu "query: ", belge "passage: ".
_QUERY_PREFIX = "query: "
_PASSAGE_PREFIX = "passage: "


class Embedder:
    """fastembed TextEmbedding sarmalayıcı; e5 prefikslerini gizler."""

    def __init__(self, model_name: str) -> None:
        from fastembed import TextEmbedding  # lazy: yalnız etkinken yüklenir

        self._model = TextEmbedding(model_name)

    def embed_query(self, text: str) -> list[float]:
        vecs = list(self._model.embed([_QUERY_PREFIX + text]))
        return [float(x) for x in vecs[0]]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        out = self._model.embed([_PASSAGE_PREFIX + t for t in texts])
        return [[float(x) for x in v] for v in out]


_embedder: Embedder | None = None


def get_embedder(settings: Settings) -> Embedder:
    """Süreç-içi singleton (model bir kez yüklenir)."""
    global _embedder
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
        lit = "[" + ",".join(repr(x) for x in qvec) + "]"
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
