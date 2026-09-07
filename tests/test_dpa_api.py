from __future__ import annotations

import asyncio
import uuid


def _bootstrap_client(client_fresh, sector="saglik"):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Buro"})
    return client_fresh.post("/api/clients", json={"name": "Klinik A.S.", "sector": sector}).json()["id"]


def _put_inv(client_fresh, cid, rows):
    assert client_fresh.put(f"/api/clients/{cid}/inventory", json={"rows": rows}).status_code == 200


ROW = {"departman": "IK", "is_sureci": "Ozluk", "alt_surec": "Bordro", "kisi_grubu": "Calisan",
       "kategoriler": ["Sağlık Bilgileri"], "amaclar": ["Bordro"], "saklama_sureleri": ["10 yil"],
       "aktarim": ["Bulut"]}


def _create_processor(client_fresh, cid, aktarim_aliases=("Bulut",)):
    r = client_fresh.post(
        f"/api/clients/{cid}/processors",
        json={"ad": "Bulut", "unvan": "Bulut A.Ş.", "aktarimAliases": list(aktarim_aliases)},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_prepare_requires_auth(client_no_account):
    r = client_no_account.post(f"/api/clients/{uuid.uuid4()}/dpa/prepare",
                                json={"processorId": str(uuid.uuid4())})
    assert r.status_code in (401, 403)


def test_prepare_unknown_client_404(client_fresh):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Buro"})
    r = client_fresh.post(f"/api/clients/{uuid.uuid4()}/dpa/prepare",
                          json={"processorId": str(uuid.uuid4())})
    assert r.status_code == 404


def test_prepare_422_when_no_match(client_fresh):
    cid = _bootstrap_client(client_fresh)
    _put_inv(client_fresh, cid, [ROW])
    pid = _create_processor(client_fresh, cid, aktarim_aliases=("BaskaTedarikci",))
    r = client_fresh.post(f"/api/clients/{cid}/dpa/prepare", json={"processorId": pid})
    assert r.status_code == 422


def test_prepare_422_when_empty_inventory(client_fresh):
    cid = _bootstrap_client(client_fresh)
    pid = _create_processor(client_fresh, cid)
    r = client_fresh.post(f"/api/clients/{cid}/dpa/prepare", json={"processorId": pid})
    assert r.status_code == 422


def test_prepare_scope(client_fresh):
    cid = _bootstrap_client(client_fresh)
    pid = _create_processor(client_fresh, cid)
    _put_inv(client_fresh, cid, [ROW])
    r = client_fresh.post(f"/api/clients/{cid}/dpa/prepare", json={"processorId": pid})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["eslesenSurecSayisi"] >= 1
    assert isinstance(body["kategoriler"], list)


def test_generate_route_mounted(client_fresh):
    cid = _bootstrap_client(client_fresh)
    pid = _create_processor(client_fresh, cid)
    _put_inv(client_fresh, cid, [ROW])
    r = client_fresh.post(f"/api/clients/{cid}/dpa/generate", json={"processorId": pid})
    assert r.status_code != 404


# --- Defekt 2: kesik DPA uretiminde doc_count geri alinir (dogrudan-fonksiyon cagrisi stili) ---

import app.config as config_module  # noqa: E402
import app.modules.dpa as dpamod  # noqa: E402
from app.auth.identity import Identity  # noqa: E402
from app.repositories import (  # noqa: E402
    ClientProcessorRepository,
    ClientRepository,
    PostgresProcessRepository,
)

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
            "kategoriler": ["Kimlik"], "veri_turleri": ["Ad"], "amaclar": ["Bordro"],
            "hukuki_sebepler": ["m.5/2-c"], "saklama_sureleri": ["10 yil"], "aktarim": ["Bulut"],
        },
    }]
    PostgresProcessRepository(db_session).replace_client(org_id, client_id, rows)
    db_session.commit()


def _make_processor_direct(db_session, client_id, org_id=_IDENT.org_id):
    p = ClientProcessorRepository(db_session).create(
        org_id, client_id, ad="Bulut", unvan="Bulut A.Ş.", aktarim_aliases=["Bulut"],
    )
    db_session.commit()
    return p.id


async def _fake_stream_truncated(*a, **k):
    yield "grounding", []
    yield "delta", "Kesik DPA sozlesmesi..."
    yield "done", {
        "model": "claude-x",
        "usage": {"inputTokens": 14000, "outputTokens": 8000},
        "stopReason": "max_tokens",
    }


def _consume(response) -> str:
    import asyncio

    async def _run():
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        return chunks

    return "".join(asyncio.run(_run()))


def test_dpa_generate_max_tokensta_belge_sayaci_geri_alinir(db_session, monkeypatch):
    """Defekt 2: kesik DPA uretiminde (stop_reason=max_tokens) belge SAKLANMADIGI icin
    dokuman kota sayaci (doc_count) da GERI ALINMALI. reserve_generation_usage ilk delta'da
    doc_count'u artirir; kesmede generated_documents geri alinir ama sayac geri alinmazsa
    kullaniciya belge verilmedigi halde '1/5 belge' kotada kalir."""
    from app.billing.entitlement import current_period
    from app.billing.repositories import UsageRepository

    _managed_billing_settings()
    monkeypatch.setattr(dpamod, "generate_dpa_envanter_stream_async", _fake_stream_truncated)
    cid = _make_client_direct(db_session)
    _put_inventory_direct(db_session, cid)
    pid = _make_processor_direct(db_session, cid)

    resp = asyncio.run(dpamod.generate(
        client_id=cid, body=dpamod.DpaGenerateIn(processor_id=pid),
        session=db_session, identity=_IDENT, x_anthropic_key=None, idempotency_key=None,
    ))
    body = _consume(resp)

    assert "event: warning" in body
    assert "event: error" not in body
    assert UsageRepository(db_session).get_count(_IDENT.org_id, current_period()) == 0
