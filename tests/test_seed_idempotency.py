"""Seed idempotency: content-hash no-op + tek-koşuculu (advisory-lock) yeniden yükleme.

Amaç (gerçek-ölçek #3): her boot'ta destructive DELETE+INSERT yerine, içerik
değişmediyse seed'i ATLA; değiştiyse tek koşucuda atomik uygula. Bu dosya saf
karar fonksiyonlarını (DB'siz) ve gözlemlenebilir DB davranışını doğrular.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Category
from app.seed import apply_seed_if_changed, compute_seed_hash, should_apply

_CATS = {"K1": {"foo": "bar"}}
_RULES = [("Tümü", "kural1")]
_PROCS = [{"sector": "S", "kisi_grubu": "KG", "departman": "D",
           "is_sureci": "IS", "alt_surec": "AS", "data": {"x": 1}}]
_MEAS = ["tedbir1"]
_REQS = [{"key": "r1", "title": "T", "madde_ref": "KVKK m.10", "description": "d",
          "group": "G", "source_type": "manual", "auto_signal": None, "sort_order": 1}]


def _inputs(categories=None):
    return dict(categories=categories or _CATS, rules=_RULES, processes=_PROCS,
                measures=_MEAS, requirements=_REQS)


def _session():
    eng = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng, expire_on_commit=False)()


# — saf fonksiyonlar (DB'siz) —

def test_compute_seed_hash_is_deterministic():
    h1 = compute_seed_hash(**_inputs())
    h2 = compute_seed_hash(**_inputs())
    assert h1 == h2 and isinstance(h1, str) and h1


def test_compute_seed_hash_changes_with_content():
    h1 = compute_seed_hash(**_inputs())
    h2 = compute_seed_hash(**_inputs(categories={"K2": {"foo": "bar"}}))
    assert h1 != h2


def test_should_apply_true_when_no_stored_hash():
    assert should_apply(None, "abc") is True


def test_should_apply_false_when_hash_matches():
    assert should_apply("abc", "abc") is False


def test_should_apply_true_when_hash_differs():
    assert should_apply("abc", "def") is True


# — DB-bağlı davranış (gözlemlenebilir) —

def test_first_run_seeds_and_records_hash():
    s = _session()
    res = apply_seed_if_changed(s, **_inputs())
    s.commit()
    assert res["skipped"] is False
    assert {c.name for c in s.query(Category).all()} == {"K1"}


def test_second_run_unchanged_skips_without_touching_data():
    s = _session()
    apply_seed_if_changed(s, **_inputs())
    s.commit()
    # seed'in silmesi gereken bir yabancı satır ekle; atlanırsa HAYATTA kalır
    s.add(Category(name="EXTRA", data={}))
    s.commit()
    res = apply_seed_if_changed(s, **_inputs())
    s.commit()
    assert res["skipped"] is True
    assert {c.name for c in s.query(Category).all()} == {"K1", "EXTRA"}


def test_changed_content_reapplies_and_replaces():
    s = _session()
    apply_seed_if_changed(s, **_inputs())
    s.commit()
    s.add(Category(name="EXTRA", data={}))
    s.commit()
    res = apply_seed_if_changed(s, **_inputs(categories={"K2": {"foo": "bar"}}))
    s.commit()
    assert res["skipped"] is False
    assert {c.name for c in s.query(Category).all()} == {"K2"}
