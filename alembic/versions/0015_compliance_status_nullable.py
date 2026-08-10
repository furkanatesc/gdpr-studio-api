"""compliance_status.status nullable (not statüsüz kaydedilebilir)

P0-1: yalnız kanıt/gerekçe notu eklemek gereksinimin statüsünü sessizce 'eksik'e
çevirmemeli. status NULL → gereksinim "değerlendirilmedi" kalır, skora sayılmaz.
Mevcut CHECK 'status IN (...)' NULL'ı geçirir (bilinmeyen != false) → değişmez.

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "compliance_status", "status",
        existing_type=sa.String(20), nullable=True,
    )


def downgrade() -> None:
    # Geri alma: null statülü satırları 'eksik'e taşı (NOT NULL'a dönmeden önce), sonra kısıtla.
    op.execute("UPDATE compliance_status SET status = 'eksik' WHERE status IS NULL")
    op.alter_column(
        "compliance_status", "status",
        existing_type=sa.String(20), nullable=False,
    )
