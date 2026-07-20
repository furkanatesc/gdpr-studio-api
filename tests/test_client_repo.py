from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Client, Organization, Process
from app.repositories import ClientRepository, PostgresProcessRepository


def _session():
    eng = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng, expire_on_commit=False)()


def _org(s):
    o = Organization(name="Büro")
    s.add(o)
    s.flush()
    return o


def test_client_crud_and_profile():
    s = _session()
    o = _org(s)
    repo = ClientRepository(s)
    c = repo.create(o.id, "Otel A.Ş.", sector="otel")
    s.commit()
    assert repo.list(o.id)[0].name == "Otel A.Ş."
    repo.update_profile(o.id, c.id, kep="a@hs01.kep.tr", legal_name="Otel A.Ş.")
    s.commit()
    assert repo.get(o.id, c.id).kep == "a@hs01.kep.tr"


def test_global_query_excludes_tenant():
    s = _session()
    o = _org(s)
    cl = Client(org_id=o.id, name="Otel")
    s.add(cl)
    s.flush()
    s.add(Process(sector="otel", kisi_grubu="Çalışan", departman="İK", is_sureci="S", alt_surec="G", data={"kategoriler": ["Kimlik"]}))
    s.add(Process(sector="otel", kisi_grubu="Çalışan", departman="İK", is_sureci="S", alt_surec="T", data={"kategoriler": ["Kimlik"]}, org_id=o.id, client_id=cl.id))
    s.commit()
    recs = PostgresProcessRepository(s).by_sector_and_group("otel", "Çalışan")
    assert len(recs) == 1 and recs[0].alt_surec == "G"


def test_replace_client_swaps_only_that_client():
    s = _session()
    o = _org(s)
    cl = Client(org_id=o.id, name="Otel")
    s.add(cl)
    s.flush()
    s.add(Process(sector="otel", kisi_grubu="Eski", departman="İK", is_sureci="S", alt_surec="A", data={}, org_id=o.id, client_id=cl.id))
    s.commit()
    n = PostgresProcessRepository(s).replace_client(o.id, cl.id, [
        {"sector": "otel", "kisi_grubu": "Yeni", "departman": "İK", "is_sureci": "S", "alt_surec": "A", "data": {}}
    ])
    s.commit()
    assert n == 1
    assert [p.kisi_grubu for p in s.query(Process).filter(Process.client_id == cl.id)] == ["Yeni"]
