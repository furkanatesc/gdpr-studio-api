from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

import app.modules.processors as procmod
from app.auth.identity import Identity
from app.repositories import ClientRepository, PostgresProcessRepository

IDENT = Identity(
    user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
    org_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
    role="yonetici", email="dev@kvkkyonetim.local",
)


def _make_client(db_session, org_id=IDENT.org_id):
    c = ClientRepository(db_session).create(org_id, "Otel", "otel")
    db_session.commit()
    return c.id


def _put_inventory(db_session, client_id, rows, org_id=IDENT.org_id):
    PostgresProcessRepository(db_session).replace_client(org_id, client_id, rows)
    db_session.commit()


def test_processor_crud_flow(db_session):
    cid = _make_client(db_session)

    created = procmod.create_processor(
        client_id=cid,
        body=procmod.ProcessorIn(ad="Bulut", unvan="Bulut A.Ş.", aktarim_aliases=["Yurt Dışı Sunucu"], yurt_disi=True),
        identity=IDENT, session=db_session,
    )
    assert created.ad == "Bulut"
    assert created.unvan == "Bulut A.Ş."
    assert created.aktarim_aliases == ["Yurt Dışı Sunucu"]
    assert created.yurt_disi is True
    pid = created.id

    listed = procmod.list_processors(client_id=cid, identity=IDENT, session=db_session)
    assert [p.ad for p in listed] == ["Bulut"]
    assert listed[0].aktarim_aliases == ["Yurt Dışı Sunucu"]

    fetched = procmod.get_processor(client_id=cid, processor_id=pid, identity=IDENT, session=db_session)
    assert fetched.id == pid
    assert fetched.ad == "Bulut"

    updated = procmod.update_processor(
        client_id=cid, processor_id=pid,
        body=procmod.ProcessorIn(ad="Bulut", unvan="Bulut A.Ş.", adres="İstanbul"),
        identity=IDENT, session=db_session,
    )
    assert updated.adres == "İstanbul"
    # update body did not include aliases -> default empty list wins (full replace semantics)
    assert updated.aktarim_aliases == []

    resp = procmod.delete_processor(client_id=cid, processor_id=pid, identity=IDENT, session=db_session)
    assert resp.status_code == 204

    assert procmod.list_processors(client_id=cid, identity=IDENT, session=db_session) == []


def test_cross_client_org_404(db_session):
    bogus_client_id = uuid.uuid4()

    with pytest.raises(HTTPException) as excinfo:
        procmod.list_processors(client_id=bogus_client_id, identity=IDENT, session=db_session)
    assert excinfo.value.status_code == 404

    with pytest.raises(HTTPException) as excinfo:
        procmod.create_processor(
            client_id=bogus_client_id,
            body=procmod.ProcessorIn(ad="X", unvan="X A.Ş."),
            identity=IDENT, session=db_session,
        )
    assert excinfo.value.status_code == 404


def test_cross_org_client_404(db_session):
    other_org_id = uuid.UUID("00000000-0000-0000-0000-000000000099")
    other_cid = _make_client(db_session, org_id=other_org_id)

    with pytest.raises(HTTPException) as excinfo:
        procmod.get_processor(client_id=other_cid, processor_id=uuid.uuid4(), identity=IDENT, session=db_session)
    assert excinfo.value.status_code == 404


def test_processor_not_found_within_owned_client_404(db_session):
    cid = _make_client(db_session)

    with pytest.raises(HTTPException) as excinfo:
        procmod.get_processor(client_id=cid, processor_id=uuid.uuid4(), identity=IDENT, session=db_session)
    assert excinfo.value.status_code == 404

    with pytest.raises(HTTPException) as excinfo:
        procmod.update_processor(
            client_id=cid, processor_id=uuid.uuid4(),
            body=procmod.ProcessorIn(ad="X", unvan="X A.Ş."),
            identity=IDENT, session=db_session,
        )
    assert excinfo.value.status_code == 404

    with pytest.raises(HTTPException) as excinfo:
        procmod.delete_processor(client_id=cid, processor_id=uuid.uuid4(), identity=IDENT, session=db_session)
    assert excinfo.value.status_code == 404


def test_aktarim_adlari_distinct_and_dedupe(db_session):
    cid = _make_client(db_session)
    rows = [
        {
            "sector": "otel", "kisi_grubu": "Calisan", "departman": "IK",
            "is_sureci": "Ozluk", "alt_surec": "Bordro",
            "data": {
                "kategoriler": ["Kimlik"], "veri_turleri": ["Ad"], "amaclar": ["Bordro"],
                "hukuki_sebepler": ["m.5/2-c"], "saklama_sureleri": ["10 yil"],
                "aktarim": ["Muhasebe Bürosu", "SGK"],
            },
        },
        {
            "sector": "otel", "kisi_grubu": "Musteri", "departman": "Satis",
            "is_sureci": "Rezervasyon", "alt_surec": "Odeme",
            "data": {
                "kategoriler": ["Kimlik"], "veri_turleri": ["Ad"], "amaclar": ["Odeme"],
                "hukuki_sebepler": ["m.5/2-c"], "saklama_sureleri": ["10 yil"],
                # duplicate-by-norm of "Muhasebe Bürosu" (case-fold, same diacritics)
                "aktarim": ["MUHASEBE BÜROSU"],
            },
        },
    ]
    _put_inventory(db_session, cid, rows)

    result = procmod.aktarim_adlari(client_id=cid, identity=IDENT, session=db_session)
    assert result.adlar == ["Muhasebe Bürosu", "SGK"]


def test_aktarim_adlari_requires_owned_client_404(db_session):
    with pytest.raises(HTTPException) as excinfo:
        procmod.aktarim_adlari(client_id=uuid.uuid4(), identity=IDENT, session=db_session)
    assert excinfo.value.status_code == 404
