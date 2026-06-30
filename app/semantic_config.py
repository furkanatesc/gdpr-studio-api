"""Semantik fallback sabitleri — tek kaynak (semantic.py + migration buradan türetir).

Bağımlılık içermez; alembic migration'ı güvenle import edebilsin diye saf tutulur.
"""

from __future__ import annotations

# Pinlenen yerel çok-dilli model (fastembed/ONNX, torch yok).
DEFAULT_SEMANTIC_MODEL = "intfloat/multilingual-e5-large"
# Modelin embedding boyutu — category_embeddings.embedding vector(N) ile BİREBİR aynı olmalı.
SEMANTIC_DIM = 1024
