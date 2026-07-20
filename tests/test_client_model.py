from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Client, Organization, Process


def _session():
    eng = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng, expire_on_commit=False)()


def test_client_belongs_to_org():
    s = _session()
    org = Organization(name="Büro")
    s.add(org)
    s.flush()
    s.add(Client(org_id=org.id, name="Otel A.Ş.", sector="otel", kep="a@hs01.kep.tr"))
    s.commit()
    c = s.query(Client).first()
    assert c.name == "Otel A.Ş." and c.sector == "otel" and c.org_id == org.id and c.mersis is None


def test_process_org_and_client_nullable():
    s = _session()
    org = Organization(name="Büro")
    s.add(org)
    s.flush()
    cl = Client(org_id=org.id, name="Otel")
    s.add(cl)
    s.flush()
    common = dict(sector="otel", kisi_grubu="Çalışan", departman="İK", is_sureci="S", alt_surec="A", data={})
    s.add(Process(**common))  # global: org_id/client_id None
    s.add(Process(**common, org_id=org.id, client_id=cl.id))  # tenant — çakışmamalı
    s.commit()
    assert s.query(Process).filter(Process.client_id.is_(None)).count() == 1
    assert s.query(Process).filter(Process.client_id == cl.id).count() == 1
