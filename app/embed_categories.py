"""Kategori embedding'lerini üretir → category_embeddings (idempotent upsert).

Çalıştırma:  python -m app.embed_categories
Önkoşul: alembic upgrade head (0006 tablosu) + seed (categories dolu).
semantic_model değişirse yeniden çalıştır (tüm satırları tazeler).
"""

from __future__ import annotations

from sqlalchemy import select, text

from .config import get_settings
from .db import get_sessionmaker
from .models import Category
from .semantic import get_embedder, to_vector_literal


def build_source_text(name: str, data: dict) -> str:
    """Kategori temsil metni: 'Ad: veri_turu1, veri_turu2, ...' (veri_turu yoksa yalnız ad)."""
    veri_turu = data.get("veri_turu") or []
    if veri_turu:
        return f"{name}: " + ", ".join(veri_turu)
    return name


def main() -> None:
    settings = get_settings()
    embedder = get_embedder(settings)
    sm = get_sessionmaker()
    with sm() as session:
        rows = session.execute(select(Category.id, Category.name, Category.data)).all()
        ids = [r.id for r in rows]
        texts = [build_source_text(r.name, r.data) for r in rows]
        vectors = embedder.embed_passages(texts)

        # idempotent: tümünü sil + yeniden ekle (20 satır; basit ve drift'siz).
        session.execute(text("DELETE FROM category_embeddings"))
        for cid, src, vec in zip(ids, texts, vectors, strict=True):
            lit = to_vector_literal(vec)
            session.execute(
                text(
                    """
                    INSERT INTO category_embeddings (category_id, embedding, source_text, model)
                    VALUES (:cid, CAST(:emb AS vector), :src, :model)
                    """
                ),
                {"cid": cid, "emb": lit, "src": src, "model": settings.semantic_model},
            )
        session.commit()
        print(f"{len(ids)} kategori embed edildi (model={settings.semantic_model}).")


if __name__ == "__main__":
    main()
