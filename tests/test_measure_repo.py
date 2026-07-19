import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Measure
from app.repositories import PostgresMeasureRepository


def _session():
    eng = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng, expire_on_commit=False)()


def test_all_measures_returns_seeded_order():
    s = _session()
    s.add_all([Measure(id=1, tedbir="Ağ güvenliği sağlanır"), Measure(id=2, tedbir="Loglama yapılır")])
    s.commit()
    assert PostgresMeasureRepository(s).all_measures() == ["Ağ güvenliği sağlanır", "Loglama yapılır"]


def test_measures_json_is_valid():
    path = Path(__file__).resolve().parent.parent / "data" / "measures.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data.get("tedbirler"), list) and data["tedbirler"]
    assert all(isinstance(t, str) and t.strip() for t in data["tedbirler"])
    assert "PROGSA" not in path.read_text(encoding="utf-8")  # gerçek kurum adı sızmamalı
