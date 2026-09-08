from __future__ import annotations

import uuid

ROW = {
    "departman": "IK", "is_sureci": "Ozluk", "alt_surec": "Bordro", "kisi_grubu": "Calisan",
    "kategoriler": ["Sağlık Bilgileri"], "veri_turleri": ["Tahlil"], "amaclar": ["Bordro"],
    "saklama_sureleri": ["10 yil"], "aktarim": ["Bulut"],
}

IHLAL_BODY = {
    "tespit": "2026-08-05T10:00:00", "tur": "Yetkisiz erişim",
    "etkilenenIndeksler": [0], "kimlikFinansal": False, "sifreli": False,
    "kisiSayisi": 50, "nasil": "x", "onlemler": "y",
}


def _bootstrap_client(client_fresh, sector="saglik"):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Buro"})
    return client_fresh.post("/api/clients", json={"name": "Klinik", "sector": sector}).json()["id"]


def _put_inv(client_fresh, cid, rows=None):
    rows = rows if rows is not None else [ROW]
    assert client_fresh.put(f"/api/clients/{cid}/inventory", json={"rows": rows}).status_code == 200


def test_ihlal_prepare_kurul_gerekli_ve_ozel_nitelikli(client_fresh):
    cid = _bootstrap_client(client_fresh)
    _put_inv(client_fresh, cid)
    r = client_fresh.post(f"/api/clients/{cid}/ihlal/prepare", json=IHLAL_BODY)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["kurulGerekli"] is True
    assert b["ilgiliKisiGerekli"] is True
    assert b["ozelNitelikliVar"] is True


def test_ihlal_prepare_requires_auth(client_no_account):
    r = client_no_account.post(
        f"/api/clients/{uuid.uuid4()}/ihlal/prepare", json=IHLAL_BODY
    )
    assert r.status_code in (401, 403)


def test_ihlal_prepare_unknown_client_404(client_fresh):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Buro"})
    r = client_fresh.post(f"/api/clients/{uuid.uuid4()}/ihlal/prepare", json=IHLAL_BODY)
    assert r.status_code == 404


def test_ihlal_index_envanter_disi_422(client_fresh):
    cid = _bootstrap_client(client_fresh)
    _put_inv(client_fresh, cid)
    body = {**IHLAL_BODY, "etkilenenIndeksler": [99]}
    r = client_fresh.post(f"/api/clients/{cid}/ihlal/prepare", json=body)
    assert r.status_code == 422


# --- generate: doğrudan çağrı deseni (test_dpia_api.py / test_kayit_api.py ile aynı) ---

import app.config as config_module  # noqa: E402
import app.modules.ihlal as ihlalmod  # noqa: E402
from app.auth.identity import Identity  # noqa: E402
from app.repositories import ClientRepository, PostgresProcessRepository  # noqa: E402

_IDENT = Identity(
    user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
    org_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
    role="yonetici", email="dev@kvkkyonetim.local",
)


def _managed_billing_settings():
    config_module._settings = config_module.Settings(
        _env_file=None, managed_anthropic_api_key="sk-managed-test",
        allowed_origins="http://localhost:3000", redis_url="",
        stripe_secret_key="sk_test_x", stripe_webhook_secret="whsec_x",
    )


def _make_client_direct(db_session, org_id=_IDENT.org_id):
    c = ClientRepository(db_session).create(org_id, "Klinik", "saglik")
    db_session.commit()
    return c.id


def _put_inventory_direct(db_session, client_id, org_id=_IDENT.org_id):
    rows = [{
        "sector": "saglik", "kisi_grubu": "Calisan", "departman": "IK",
        "is_sureci": "Ozluk", "alt_surec": "Bordro",
        "data": {
            "kategoriler": ["Sağlık Bilgileri"], "veri_turleri": ["Tahlil"], "amaclar": ["Bordro"],
            "hukuki_sebepler": ["m.5/2-c"], "saklama_sureleri": ["10 yil"], "aktarim": ["SGK"],
        },
    }]
    PostgresProcessRepository(db_session).replace_client(org_id, client_id, rows)
    db_session.commit()


async def _fake_ihlal_stream(*a, **k):
    yield "delta", "İhlal bildirim metni..."
    yield "done", {"model": "claude-x", "usage": {"inputTokens": 10, "outputTokens": 20}}


async def _fake_ihlal_stream_truncated(*a, **k):
    yield "delta", "Kesik ihlal metni..."
    yield "done", {
        "model": "claude-x",
        "usage": {"inputTokens": 14000, "outputTokens": 8000},
        "stopReason": "max_tokens",
    }


def _consume_direct(response) -> str:
    import asyncio

    async def _run():
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        return chunks

    return "".join(asyncio.run(_run()))


def _generate_direct(db_session, client_id, **ov):
    import asyncio

    kwargs = dict(
        session=db_session, identity=_IDENT,
        body=ihlalmod.IhlalGenerateIn(
            tespit="2026-08-05T10:00:00", tur="Yetkisiz erişim",
            etkilenen_indeksler=[0], kimlik_finansal=False, sifreli=False,
            kisi_sayisi=50, nasil="x", onlemler="y", bildirim_turu="kurul",
        ),
        x_anthropic_key=None, idempotency_key=None,
    )
    kwargs.update(ov)
    return asyncio.run(ihlalmod.generate(client_id=client_id, **kwargs))


def test_ihlal_generate_kurul_sse_persist_yok(db_session, monkeypatch):
    from app.models import ClientDocument

    _managed_billing_settings()
    monkeypatch.setattr(ihlalmod, "generate_ihlal_stream_async", _fake_ihlal_stream)
    cid = _make_client_direct(db_session)
    _put_inventory_direct(db_session, cid)

    resp = _generate_direct(db_session, cid)
    body = _consume_direct(resp)

    assert "event: done" in body
    assert "event: error" not in body
    assert db_session.query(ClientDocument).filter_by(client_id=cid).count() == 0


def test_ihlal_generate_gecersiz_tur_422(db_session, monkeypatch):
    from fastapi import HTTPException

    _managed_billing_settings()
    monkeypatch.setattr(ihlalmod, "generate_ihlal_stream_async", _fake_ihlal_stream)
    cid = _make_client_direct(db_session)
    _put_inventory_direct(db_session, cid)

    body = ihlalmod.IhlalGenerateIn(
        tespit="2026-08-05T10:00:00", tur="Yetkisiz erişim",
        etkilenen_indeksler=[0], kimlik_finansal=False, sifreli=False,
        kisi_sayisi=50, nasil="x", onlemler="y", bildirim_turu="x",
    )
    try:
        _generate_direct(db_session, cid, body=body)
    except HTTPException as e:
        assert e.status_code == 422
    else:
        raise AssertionError("422 bekleniyordu")


def test_ihlal_generate_max_tokensta_sayac_geri_alinir(db_session, monkeypatch):
    from app.billing.entitlement import current_period
    from app.billing.repositories import UsageRepository
    from app.models import ClientDocument

    _managed_billing_settings()
    monkeypatch.setattr(ihlalmod, "generate_ihlal_stream_async", _fake_ihlal_stream_truncated)
    cid = _make_client_direct(db_session)
    _put_inventory_direct(db_session, cid)

    resp = _generate_direct(db_session, cid)
    body = _consume_direct(resp)

    assert "event: warning" in body
    assert "event: error" not in body
    assert db_session.query(ClientDocument).filter_by(client_id=cid).count() == 0
    assert UsageRepository(db_session).get_count(_IDENT.org_id, current_period()) == 0
