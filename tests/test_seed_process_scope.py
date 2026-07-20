"""seed() Process silmesi YALNIZ global grounding'i hedefler — müvekkil envanterine dokunmaz.

Kritik: seed her deploy'da çalışır. Filtresiz delete(Process), müvekkillerin yüklediği
envanteri silerdi. Bu test o kapsamı (org_id IS NULL AND client_id IS NULL) sabitler.
"""
import uuid

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Process


def _session():
    eng = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng, expire_on_commit=False)()


def test_global_silinir_muvekkil_korunur():
    s = _session()
    org, client = uuid.uuid4(), uuid.uuid4()
    s.add(Process(sector="otel", kisi_grubu="Çalışan", departman="İK",
                  is_sureci="Özlük", alt_surec="Bordro", data={}))  # global (NULL/NULL)
    s.add(Process(sector="otel", kisi_grubu="Ziyaretçi", departman="Güvenlik",
                  is_sureci="Kamera", alt_surec="Kayıt", data={},
                  org_id=org, client_id=client))  # müvekkil envanteri
    s.commit()

    # seed()'deki ile AYNI delete cümlesi.
    s.execute(delete(Process).where(Process.org_id.is_(None), Process.client_id.is_(None)))
    s.commit()

    kalan = s.scalars(select(Process)).all()
    assert len(kalan) == 1, "yalnız müvekkil satırı kalmalı"
    assert kalan[0].client_id == client, "müvekkil envanteri korunmalı"
    assert kalan[0].org_id == org
