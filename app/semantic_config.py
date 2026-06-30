"""Semantik fallback sabitleri — tek kaynak (semantic.py + migration buradan türetir).

Bağımlılık içermez; alembic migration'ı güvenle import edebilsin diye saf tutulur.
"""

# Pinlenen yerel çok-dilli model (fastembed/ONNX, torch yok).
DEFAULT_SEMANTIC_MODEL = "intfloat/multilingual-e5-large"
# Modelin embedding boyutu — category_embeddings.embedding vector(N) ile BİREBİR aynı olmalı.
SEMANTIC_DIM = 1024
