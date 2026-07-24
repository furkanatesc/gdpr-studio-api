from __future__ import annotations

import uuid

import app.config as config_module
import app.modules.kayit as kayitmod
from app.auth.identity import Identity
from app.repositories import ClientRepository, PostgresProcessRepository

IDENT = Identity(
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


def _make_client(db_session, org_id=IDENT.org_id):
    c = ClientRepository(db_session).create(org_id, "Otel", "otel")
    db_session.commit()
    return c.id


def _put_inventory(db_session, client_id, org_id=IDENT.org_id):
    # replace_client satir sekli: {sector, kisi_grubu, departman, is_sureci, alt_surec, data:{...}}
    # data JSONB _to_record'un okudugu anahtarlari tasir (kategoriler, veri_turleri, ... aktarim).
    rows = [{
        "sector": "otel", "kisi_grubu": "Calisan", "departman": "IK",
        "is_sureci": "Ozluk", "alt_surec": "Bordro",
        "data": {
            "kategoriler": ["Kimlik"], "veri_turleri": ["Ad"], "amaclar": ["Bordro"],
            "hukuki_sebepler": ["m.5/2-c"], "saklama_sureleri": ["10 yil"], "aktarim": ["SGK"],
        },
    }]
    PostgresProcessRepository(db_session).replace_client(org_id, client_id, rows)
    db_session.commit()


def _fake_stream(*a, **k):
    yield "grounding", []
    yield "delta", "Isleme"
    yield "delta", " kaydi."
    yield "done", {"model": "claude-x", "usage": {"inputTokens": 10, "outputTokens": 20}}


def _consume(response) -> str:
    import asyncio

    async def _run():
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        return chunks

    return "".join(asyncio.run(_run()))


def _generate(db_session, client_id, **ov):
    kwargs = dict(session=db_session, identity=IDENT, x_anthropic_key=None, idempotency_key=None)
    kwargs.update(ov)
    return kayitmod.generate(client_id=client_id, **kwargs)


def test_kayit_generate_musvekkil_yok_404(db_session, monkeypatch):
    _managed_billing_settings()
    monkeypatch.setattr(kayitmod, "generate_kayit_envanter_stream", _fake_stream)
    from fastapi import HTTPException
    try:
        _generate(db_session, uuid.uuid4())
    except HTTPException as e:
        assert e.status_code == 404
    else:
        raise AssertionError("404 bekleniyordu")


def test_kayit_generate_envanter_bos_422(db_session, monkeypatch):
    _managed_billing_settings()
    monkeypatch.setattr(kayitmod, "generate_kayit_envanter_stream", _fake_stream)
    cid = _make_client(db_session)
    from fastapi import HTTPException
    try:
        _generate(db_session, cid)
    except HTTPException as e:
        assert e.status_code == 422
    else:
        raise AssertionError("422 bekleniyordu")


def test_kayit_generate_belgeyi_saklar(db_session, monkeypatch):
    from app.models import ClientDocument
    _managed_billing_settings()
    monkeypatch.setattr(kayitmod, "generate_kayit_envanter_stream", _fake_stream)
    cid = _make_client(db_session)
    _put_inventory(db_session, cid)

    resp = _generate(db_session, cid)
    _consume(resp)

    rows = db_session.query(ClientDocument).filter_by(client_id=cid).all()
    assert len(rows) == 1
    assert rows[0].doc_type == "kayit"
    assert rows[0].title == "İşleme Kaydı"
    assert "kaydi." in rows[0].content
    # kisi_grubu+kategori+amac+hukuki_sebep+saklama+aktarim: 6/6 dolu -> 1.0
    assert rows[0].score_completeness == 1.0
    assert rows[0].score_compliance == 0.0  # org'da uyum statusu yok


def test_kayit_generate_baska_org_muvekkili_404(db_session, monkeypatch):
    """client_processes(client_id) org filtresi tasimaz; tek savunma ClientRepository.get
    sahiplik kontrolunun envanter okumasindan once gelmesidir. Baska org'un muvekkilinin
    client_id'si mevcut kimlikle 404 vermeli ve envanteri sizdirmamali."""
    from app.models import ClientDocument

    _managed_billing_settings()
    monkeypatch.setattr(kayitmod, "generate_kayit_envanter_stream", _fake_stream)
    other_org_id = uuid.UUID("00000000-0000-0000-0000-000000000099")
    other_cid = _make_client(db_session, org_id=other_org_id)
    _put_inventory(db_session, other_cid, org_id=other_org_id)

    from fastapi import HTTPException
    try:
        _generate(db_session, other_cid)
    except HTTPException as e:
        assert e.status_code == 404
    else:
        raise AssertionError("404 bekleniyordu")

    rows = db_session.query(ClientDocument).filter_by(client_id=other_cid).all()
    assert len(rows) == 0
