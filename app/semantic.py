"""Yerel embedding (fastembed/ONNX) + Postgres pgvector semantik matcher.

fastembed yalnız bu modülde import edilir (lazy): semantic_fallback_enabled
kapalıyken Embedder hiç kurulmaz, model yüklenmez. legal_core saf kalır.
"""

from __future__ import annotations

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
