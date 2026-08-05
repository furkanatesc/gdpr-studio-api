from __future__ import annotations

import uuid


def _bootstrap_client(client_fresh, sector="saglik"):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Buro"})
    return client_fresh.post("/api/clients", json={"name": "Klinik A.S.", "sector": sector}).json()["id"]


def _put_inv(client_fresh, cid, rows):
    assert client_fresh.put(f"/api/clients/{cid}/inventory", json={"rows": rows}).status_code == 200


ROW = {"departman": "IK", "is_sureci": "Ozluk", "alt_surec": "Bordro", "kisi_grubu": "Calisan",
       "kategoriler": ["Sağlık Bilgileri"], "amaclar": ["Bordro"], "saklama_sureleri": ["10 yil"]}


def test_prepare_requires_auth(client_no_account):
    r = client_no_account.post(f"/api/clients/{uuid.uuid4()}/dpia/prepare",
                               json={"anket": {"buyukOlcek": False, "yeniTeknoloji": False,
                                               "savunmasizGrup": False, "veriEslestirme": False}})
    assert r.status_code in (401, 403)


def test_prepare_unknown_client_404(client_fresh):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Buro"})
    r = client_fresh.post(f"/api/clients/{uuid.uuid4()}/dpia/prepare",
                          json={"anket": {"buyukOlcek": False, "yeniTeknoloji": False,
                                          "savunmasizGrup": False, "veriEslestirme": False}})
    assert r.status_code == 404


def test_prepare_empty_inventory_422(client_fresh):
    cid = _bootstrap_client(client_fresh)
    r = client_fresh.post(f"/api/clients/{cid}/dpia/prepare",
                          json={"anket": {"buyukOlcek": False, "yeniTeknoloji": False,
                                          "savunmasizGrup": False, "veriEslestirme": False}})
    assert r.status_code == 422


def test_prepare_verdict_ozel_nitelikli_plus_anket(client_fresh):
    cid = _bootstrap_client(client_fresh)
    _put_inv(client_fresh, cid, [ROW])  # Sağlık = özel nitelikli (auto)
    r = client_fresh.post(f"/api/clients/{cid}/dpia/prepare",
                          json={"anket": {"buyukOlcek": False, "yeniTeknoloji": False,
                                          "savunmasizGrup": True, "veriEslestirme": False}})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["otomatik"]["ozelNitelikliVar"] is True
    assert b["kriterSayisi"] == 2
    assert b["zorunlu"] is True


def test_generate_route_mounted(client_fresh):
    cid = _bootstrap_client(client_fresh)
    _put_inv(client_fresh, cid, [ROW])
    # API key yok/dev-bypass: en azindan 422/erisim degil, akis baslar veya kota/By key hatasi
    r = client_fresh.post(f"/api/clients/{cid}/dpia/generate", json={"tetiklenenler": ["ozel_nitelikli"]})
    assert r.status_code != 404  # mount dogrulamasi (kayit test deseni)


# --- Defekt 2: kesme -> doc_count geri alinir (kayit test deseni; dogrudan fonksiyon cagrisi) ---

import app.config as config_module  # noqa: E402
import app.modules.dpia as dpiamod  # noqa: E402
from app.auth.identity import Identity  # noqa: E402
from app.repositories import (  # noqa: E402
    ClientRepository,
    PostgresProcessRepository,
)

_DEFEKT2_IDENT = Identity(
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


def _make_client_direct(db_session, org_id=_DEFEKT2_IDENT.org_id):
    c = ClientRepository(db_session).create(org_id, "Klinik", "saglik")
    db_session.commit()
    return c.id


def _put_inventory_direct(db_session, client_id, org_id=_DEFEKT2_IDENT.org_id):
    rows = [{
        "sector": "saglik", "kisi_grubu": "Calisan", "departman": "IK",
        "is_sureci": "Ozluk", "alt_surec": "Bordro",
        "data": {
            "kategoriler": ["Sağlık Bilgileri"], "veri_turleri": ["Ad"], "amaclar": ["Bordro"],
            "hukuki_sebepler": ["m.5/2-c"], "saklama_sureleri": ["10 yil"], "aktarim": ["SGK"],
        },
    }]
    PostgresProcessRepository(db_session).replace_client(org_id, client_id, rows)
    db_session.commit()


def _fake_dpia_stream_truncated(*a, **k):
    yield "grounding", []
    yield "delta", "Kesik DPIA metni..."
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
    kwargs = dict(
        session=db_session, identity=_DEFEKT2_IDENT,
        body=dpiamod.DpiaGenerateIn(tetiklenenler=["ozel_nitelikli"]),
        x_anthropic_key=None, idempotency_key=None,
    )
    kwargs.update(ov)
    return dpiamod.generate(client_id=client_id, **kwargs)


def test_dpia_generate_max_tokensta_belge_sayaci_geri_alinir(db_session, monkeypatch):
    """Defekt 2: kesik uretimde (stop_reason=max_tokens) belge SAKLANMADIGI icin dokuman
    kota sayaci (doc_count) da GERI ALINMALI. reserve_generation_usage ilk delta'da
    doc_count'u artirir; kesmede generated_documents geri alinir ama sayac geri
    alinmazsa '1/5 belge' kotada kalir (kayit'taki referans fix ile ayni desen)."""
    from app.billing.entitlement import current_period
    from app.billing.repositories import UsageRepository

    _managed_billing_settings()
    monkeypatch.setattr(dpiamod, "generate_dpia_envanter_stream", _fake_dpia_stream_truncated)
    cid = _make_client_direct(db_session)
    _put_inventory_direct(db_session, cid)

    resp = _generate_direct(db_session, cid)
    body = _consume_direct(resp)

    assert "event: warning" in body
    assert "event: error" not in body
    assert UsageRepository(db_session).get_count(_DEFEKT2_IDENT.org_id, current_period()) == 0
