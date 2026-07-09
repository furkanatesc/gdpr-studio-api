"""compliance_requirements seed yükleyici — idempotent (delete-all + insert).

İçerik (gerçek gereksinim listesi) T7'de doldurulur; REQUIREMENTS şimdilik boştur
(içerik-bağımsız iskelet — KVKK verisi uydurulmaz). embed_categories backfill deseni gibi.

Çalıştırma:  python -m app.seed_compliance
Önkoşul: alembic upgrade head (0007 tablosu).
"""

from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.orm import Session

from .db import get_sessionmaker
from .models import ComplianceRequirement

# T7 (BLOKLU): gerçek liste gelince doldurulur. Her kalem:
# {key, title, madde_ref, description, group, source_type, auto_signal, sort_order}
REQUIREMENTS: list[dict] = []


def seed_compliance_requirements(session: Session, requirements: list[dict]) -> int:
    """Gereksinim referans tablosunu idempotent yükler: tümünü sil + yeniden ekle.

    Global referans veri (tenant'a bağlı değil); delete+insert drift'siz ve basit.
    Yüklenen satır sayısını döndürür.
    """
    session.execute(delete(ComplianceRequirement))
    session.add_all([ComplianceRequirement(**r) for r in requirements])
    session.flush()
    return len(requirements)


def main() -> None:
    sm = get_sessionmaker()
    with sm() as session:
        n = seed_compliance_requirements(session, REQUIREMENTS)
        session.commit()
        print(f"{n} uyum gereksinimi yüklendi.")


if __name__ == "__main__":
    main()
