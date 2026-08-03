"""ClientProcessorRepository CRUD testleri (SQLite in-memory, gercek-PG gerektirmez)."""
from __future__ import annotations

import uuid

from app.models import Client, Organization
from app.repositories import ClientProcessorRepository


def _seed_org_and_client(db_session) -> tuple[uuid.UUID, uuid.UUID]:
    org = Organization(name="Test Org")
    db_session.add(org)
    db_session.flush()
    client = Client(org_id=org.id, name="Test Client")
    db_session.add(client)
    db_session.flush()
    db_session.commit()
    return org.id, client.id


def test_create_list_get_update_delete(db_session):
    org_id, client_id = _seed_org_and_client(db_session)
    repo = ClientProcessorRepository(db_session)

    created = repo.create(
        org_id,
        client_id,
        ad="Bulut",
        unvan="Bulut A.Ş.",
        aktarim_aliases=["Yurt Dışı Sunucu"],
        yurt_disi=True,
    )
    db_session.commit()

    assert created.id is not None
    assert created.aktarim_aliases == ["Yurt Dışı Sunucu"]

    listed = repo.list(org_id, client_id)
    assert [p.ad for p in listed] == ["Bulut"]

    fetched = repo.get(org_id, client_id, created.id)
    assert fetched is not None
    assert fetched.unvan == "Bulut A.Ş."
    assert isinstance(fetched.aktarim_aliases, list)

    updated = repo.update(org_id, client_id, created.id, adres="İstanbul", alt_isleyen_var=True)
    db_session.commit()
    assert updated is not None
    assert updated.adres == "İstanbul"
    assert updated.alt_isleyen_var is True

    assert repo.get(org_id, client_id, created.id).adres == "İstanbul"

    assert repo.delete(org_id, client_id, created.id) is True
    db_session.commit()
    assert repo.list(org_id, client_id) == []
    assert repo.get(org_id, client_id, created.id) is None


def test_get_and_delete_missing_returns_none_or_false(db_session):
    org_id, client_id = _seed_org_and_client(db_session)
    repo = ClientProcessorRepository(db_session)
    missing_id = uuid.uuid4()

    assert repo.get(org_id, client_id, missing_id) is None
    assert repo.update(org_id, client_id, missing_id, adres="x") is None
    assert repo.delete(org_id, client_id, missing_id) is False


def test_default_aktarim_aliases_is_empty_list(db_session):
    org_id, client_id = _seed_org_and_client(db_session)
    repo = ClientProcessorRepository(db_session)

    created = repo.create(org_id, client_id, ad="Depo", unvan="Depo Ltd.")
    db_session.commit()

    assert created.aktarim_aliases == []
