"""category_embeddings tablosu (semantik fallback, pgvector — Postgres-only)

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-29
"""
from typing import Sequence, Union

from alembic import op

from app.semantic_config import SEMANTIC_DIM

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pgvector extension (docker imajı pgvector/pgvector:pg16; CI servisi de aynı olmalı).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # categories global (org_id yok, RLS yok) → bu tablo da global, RLS YOK.
    op.execute(
        f"""
        CREATE TABLE category_embeddings (
            category_id INTEGER PRIMARY KEY REFERENCES categories(id) ON DELETE CASCADE,
            embedding vector({SEMANTIC_DIM}) NOT NULL,
            source_text TEXT NOT NULL,
            model TEXT NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS category_embeddings")
    # vector extension'ı düşürme (başka kullanım olabilir).
