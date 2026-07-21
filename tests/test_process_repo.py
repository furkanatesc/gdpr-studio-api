import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Process
from app.repositories import PostgresProcessRepository


def _session():
    eng = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng, expire_on_commit=False)()


def _add(s, sector, kisi_grubu, dep="İK", isr="İşe Giriş", alt="Kimlik teyidi", data=None):
    s.add(Process(
        sector=sector, kisi_grubu=kisi_grubu, departman=dep, is_sureci=isr, alt_surec=alt,
        data=data or {"kategoriler": ["Kimlik"], "saklama_sureleri": ["10 yıl"]},
    ))


def test_by_sector_and_group_filters():
    s = _session()
    _add(s, "sirket", "Çalışan")
    _add(s, "sirket", "Çalışan Adayı", alt="Başvuru")
    _add(s, "otel", "Çalışan", dep="TEKNİK")
    s.commit()
    recs = PostgresProcessRepository(s).by_sector_and_group("sirket", "Çalışan")
    assert len(recs) == 1
    assert recs[0].departman == "İK"
    assert recs[0].saklama_sureleri == ["10 yıl"]


def test_by_sector_and_group_none_returns_all_for_sector():
    s = _session()
    _add(s, "sirket", "Çalışan")
    _add(s, "sirket", "Çalışan Adayı", alt="Başvuru")
    _add(s, "otel", "Çalışan")
    s.commit()
    recs = PostgresProcessRepository(s).by_sector_and_group("sirket", None)
    assert len(recs) == 2  # sektör izolasyonu: otel gelmez


def test_person_groups_sorted_and_distinct():
    s = _session()
    _add(s, "sirket", "Çalışan")
    _add(s, "sirket", "Çalışan", alt="Başka")
    _add(s, "sirket", "Ziyaretçi", alt="Giriş")
    _add(s, "otel", "Tedarikçi Çalışanı")
    s.commit()
    assert PostgresProcessRepository(s).person_groups("sirket") == ["Çalışan", "Ziyaretçi"]


def test_to_record_derives_aktarim_toplama_from_verbis_fields():
    s = _session()
    _add(s, "sirket", "Çalışan", data={
        "kaynak": "İlgili kişinin kendisi",
        "alici_grubu": ["SGK"],
        "aktarim_metodu": "Elektronik",
        "yurtdisi_aktarim": "Evet",
    })
    s.commit()
    rec = PostgresProcessRepository(s).by_sector_and_group("sirket", "Çalışan")[0]
    assert rec.toplama == ["İlgili kişinin kendisi"]
    assert "SGK" in rec.aktarim
    assert "Elektronik" in rec.aktarim
    assert "Yurt dışına aktarım" in rec.aktarim


def test_to_record_derives_aktarim_toplama_from_anket_fields():
    s = _session()
    _add(s, "sirket", "Çalışan", data={"aktarim": ["X"], "toplama": ["Y"]})
    s.commit()
    rec = PostgresProcessRepository(s).by_sector_and_group("sirket", "Çalışan")[0]
    assert rec.aktarim == ["X"]
    assert rec.toplama == ["Y"]


def test_to_record_derives_empty_aktarim_toplama_when_no_data():
    s = _session()
    _add(s, "sirket", "Çalışan", data={})
    s.commit()
    rec = PostgresProcessRepository(s).by_sector_and_group("sirket", "Çalışan")[0]
    assert rec.aktarim == []
    assert rec.toplama == []


def test_processes_json_is_valid_and_seedable():
    """Commit'li şablon kütüphanesi: geçerli JSON + şema + kanonik kişi grubu."""
    from pathlib import Path

    from app.sectors import SECTORS

    path = Path(__file__).resolve().parent.parent / "data" / "processes.json"
    procs = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(procs, list) and procs
    for p in procs:
        assert p["sector"] in SECTORS
        assert p["kisi_grubu"] and p["departman"] is not None
        assert isinstance(p["data"], dict)
        assert isinstance(p["data"]["saklama_sureleri"], list)
    # anonimleştirme + alias doğrulaması
    blob = path.read_text(encoding="utf-8")
    assert "PROGSA" not in blob  # gerçek kurum adı sızmamalı
    groups = {p["kisi_grubu"] for p in procs}
    assert "Tederikçi Yetkilisi" not in groups  # alias ile düzeltildi
