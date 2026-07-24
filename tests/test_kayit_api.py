from __future__ import annotations

import uuid

import app.config as config_module
import app.idempotency as idem
import app.modules.kayit as kayitmod
import app.redis_client as rc
from app.auth.identity import Identity
from app.models import GeneratedDocument
from app.repositories import (
    ClientRepository,
    GeneratedDocumentRepository,
    PostgresProcessRepository,
)
from legal_core.models import DocType

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


def _fake_stream_truncated(*a, **k):
    yield "grounding", []
    yield "delta", "Kesik VERBIS tablosu..."
    yield "done", {
        "model": "claude-x",
        "usage": {"inputTokens": 14000, "outputTokens": 8000},
        "stopReason": "max_tokens",
    }


def test_kayit_generate_max_tokensta_saklanmaz_ve_uyari_yayinlanir(db_session, monkeypatch):
    """Borc: kesik uretim (stop_reason=max_tokens) tam puanla resmi kayit gibi
    SAKLANMAMALI ve istemci acik bir 'warning' SSE olayi almali (error DEGIL)."""
    from app.models import ClientDocument

    _managed_billing_settings()
    monkeypatch.setattr(kayitmod, "generate_kayit_envanter_stream", _fake_stream_truncated)
    cid = _make_client(db_session)
    _put_inventory(db_session, cid)

    resp = _generate(db_session, cid)
    body = _consume(resp)

    assert "event: warning" in body
    assert "event: error" not in body
    rows = db_session.query(ClientDocument).filter_by(client_id=cid).all()
    assert len(rows) == 0


class _FakeRedis:
    """set(nx, ex) + delete destekleyen minimum sahte Redis (TTL simüle edilmez)."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def set(self, key: str, value: str, nx: bool = False, ex: int | None = None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    def delete(self, key: str) -> int:
        return 1 if self.store.pop(key, None) is not None else 0

    def ping(self) -> bool:
        return True


def _use_fake_redis(monkeypatch) -> _FakeRedis:
    fake = _FakeRedis()
    monkeypatch.setattr(idem, "get_redis", lambda: fake)
    monkeypatch.setattr(rc, "get_redis", lambda: fake)
    return fake


def test_kayit_generate_uyari_donedan_once_gelir(db_session, monkeypatch):
    """Borc #1: 'warning' 'done'dan ONCE gelmeli; done payload'inda ek sigorta alanlari olmali."""
    import json

    _managed_billing_settings()
    monkeypatch.setattr(kayitmod, "generate_kayit_envanter_stream", _fake_stream_truncated)
    cid = _make_client(db_session)
    _put_inventory(db_session, cid)

    resp = _generate(db_session, cid)
    body = _consume(resp)

    assert "event: warning" in body and "event: done" in body
    assert body.index("event: warning") < body.index("event: done")

    done_line = [ln for ln in body.splitlines() if ln.startswith("data: ")][-1]
    done_payload = json.loads(done_line[len("data: "):])
    assert done_payload["incomplete"] is True
    assert done_payload["warningMessage"]


def test_kayit_generate_max_tokensta_uyum_kaydi_geri_alinir(db_session, monkeypatch):
    """Borc #2: kesmede generated_documents satiri SAYILMAMALI; org'un ONCEKI gecerli
    kaydi ETKILENMEMELI."""
    _managed_billing_settings()
    GeneratedDocumentRepository(db_session).record(IDENT.org_id, DocType.kayit)
    db_session.commit()

    monkeypatch.setattr(kayitmod, "generate_kayit_envanter_stream", _fake_stream_truncated)
    cid = _make_client(db_session)
    _put_inventory(db_session, cid)

    resp = _generate(db_session, cid)
    _consume(resp)

    rows = db_session.query(GeneratedDocument).filter_by(doc_type="kayit").all()
    assert len(rows) == 1


def _fake_stream_with_stop_reason(stop_reason):
    def _f(*a, **k):
        yield "grounding", []
        yield "delta", "Isleme kaydi metni"
        yield "done", {
            "model": "claude-x",
            "usage": {"inputTokens": 10, "outputTokens": 20},
            "stopReason": stop_reason,
        }

    return _f


def test_kayit_generate_baglam_penceresi_asildiginda_saklanmaz(db_session, monkeypatch):
    """Borc #3: model_context_window_exceeded da kesme sayilmali."""
    from app.models import ClientDocument

    _managed_billing_settings()
    monkeypatch.setattr(
        kayitmod, "generate_kayit_envanter_stream",
        _fake_stream_with_stop_reason("model_context_window_exceeded"),
    )
    cid = _make_client(db_session)
    _put_inventory(db_session, cid)

    resp = _generate(db_session, cid)
    body = _consume(resp)

    assert "event: warning" in body
    assert db_session.query(ClientDocument).filter_by(client_id=cid).count() == 0
    assert db_session.query(GeneratedDocument).filter_by(doc_type="kayit").count() == 0


def test_kayit_generate_refusal_saklanmaz_ve_farkli_mesaj_gosterilir(db_session, monkeypatch):
    """Borc #3: refusal SAKLANMAZ ama mesaji uzunluk-kesme mesajindan FARKLI olmali."""
    from app.models import ClientDocument

    _managed_billing_settings()
    monkeypatch.setattr(
        kayitmod, "generate_kayit_envanter_stream",
        _fake_stream_with_stop_reason("refusal"),
    )
    cid = _make_client(db_session)
    _put_inventory(db_session, cid)

    resp = _generate(db_session, cid)
    body = _consume(resp)

    assert "event: warning" in body
    assert "generation_refused" in body
    assert "truncated_output_limit" not in body
    assert db_session.query(ClientDocument).filter_by(client_id=cid).count() == 0
    assert db_session.query(GeneratedDocument).filter_by(doc_type="kayit").count() == 0


def test_kayit_generate_end_turn_saklanir_regresyon_kilidi(db_session, monkeypatch):
    """Regresyon kilidi: stopReason='end_turn' -> belge HALA saklanir."""
    from app.models import ClientDocument

    _managed_billing_settings()
    monkeypatch.setattr(
        kayitmod, "generate_kayit_envanter_stream",
        _fake_stream_with_stop_reason("end_turn"),
    )
    cid = _make_client(db_session)
    _put_inventory(db_session, cid)

    resp = _generate(db_session, cid)
    body = _consume(resp)

    assert "event: warning" not in body
    rows = db_session.query(ClientDocument).filter_by(client_id=cid).all()
    assert len(rows) == 1
    assert db_session.query(GeneratedDocument).filter_by(doc_type="kayit").count() == 1


def test_kayit_generate_kesmede_idempotency_kilidi_birakilir(db_session, monkeypatch):
    """Borc #4: kesmede idempotency kilidi BIRAKILMALI."""
    _managed_billing_settings()
    fake = _use_fake_redis(monkeypatch)
    monkeypatch.setattr(kayitmod, "generate_kayit_envanter_stream", _fake_stream_truncated)
    cid = _make_client(db_session)
    _put_inventory(db_session, cid)

    resp = _generate(db_session, cid, idempotency_key="kayit-kesme-1")
    _consume(resp)

    assert fake.store == {}


def test_kayit_generate_global_kurallar_dahil(db_session, monkeypatch):
    """I2: app/modules/kayit.py yalniz doc_type='kayit' kurallarini degil GLOBAL_RULES'u
    da (ozellikle yurt disi aktarim kurali) generate_kayit_envanter_stream'e gecirmeli."""
    _managed_billing_settings()
    captured = {}

    def _capture_stream(records, profile, measures, rules, **kw):
        captured["rules"] = rules
        yield from _fake_stream()

    monkeypatch.setattr(kayitmod, "generate_kayit_envanter_stream", _capture_stream)
    cid = _make_client(db_session)
    _put_inventory(db_session, cid)

    resp = _generate(db_session, cid)
    _consume(resp)

    assert any("YURT DIŞI AKTARIM" in r for r in captured["rules"])


def test_kayit_generate_puan_a_cap_ile_tutarli(db_session, monkeypatch):
    """I4: process_cap'ten fazla surec varsa Puan A yalniz prompt'a giren (capli) kumeden
    hesaplanmali; aksi halde belgedeki her sey tam oldugu halde puan yanlis dusuk gorunur."""
    from app.models import ClientDocument

    _managed_billing_settings()
    config_module._settings.process_cap = 1
    monkeypatch.setattr(kayitmod, "generate_kayit_envanter_stream", _fake_stream)
    cid = _make_client(db_session)

    # Ilk satir tam dolu (6/6), ikinci satir tamamen bos (0/6). Cap=1 -> yalniz ilk satir sayilmali.
    rows = [
        {
            "sector": "otel", "kisi_grubu": "Calisan", "departman": "IK",
            "is_sureci": "Ozluk", "alt_surec": "Bordro",
            "data": {
                "kategoriler": ["Kimlik"], "veri_turleri": ["Ad"], "amaclar": ["Bordro"],
                "hukuki_sebepler": ["m.5/2-c"], "saklama_sureleri": ["10 yil"], "aktarim": ["SGK"],
            },
        },
        {
            "sector": "otel", "kisi_grubu": "", "departman": "IK",
            "is_sureci": "Zbos", "alt_surec": "Zbos",
            "data": {
                "kategoriler": [], "veri_turleri": [], "amaclar": [],
                "hukuki_sebepler": [], "saklama_sureleri": [], "aktarim": [],
            },
        },
    ]
    PostgresProcessRepository(db_session).replace_client(IDENT.org_id, cid, rows)
    db_session.commit()

    resp = _generate(db_session, cid)
    _consume(resp)

    doc = db_session.query(ClientDocument).filter_by(client_id=cid).one()
    assert doc.score_completeness == 1.0


def test_kayit_generate_saglayiciya_32000_max_tokens_ile_cagirir(db_session, monkeypatch):
    """Kayit uretimi settings.max_tokens (8000) DEGIL, kayit'e ozel 32000 tavanini
    saglayiciya gecirmeli (200+ surecli envanterler 8000'de kesiliyordu)."""
    _managed_billing_settings()
    captured = {}

    def _capture_stream(records, profile, measures, rules, **kw):
        captured["max_tokens"] = kw.get("max_tokens")
        yield from _fake_stream()

    monkeypatch.setattr(kayitmod, "generate_kayit_envanter_stream", _capture_stream)
    cid = _make_client(db_session)
    _put_inventory(db_session, cid)

    resp = _generate(db_session, cid)
    _consume(resp)

    assert captured["max_tokens"] == 32000


def test_kayit_generate_rezervasyon_32000_uzerinden_hesaplanir(db_session, monkeypatch):
    """Maliyet rezervasyonu kayit akisinda gercekte kullanilan 32000 tavanini gecirmeli;
    aksi halde settings.max_tokens (8000) uzerinden eksik rezerve edilir ve maliyet
    guardrail'i (COST_BUDGET_MICROS) 200+ surecli kayit uretimlerinde atlatilabilir."""
    _managed_billing_settings()
    captured = {}
    real_reserve = kayitmod.reserve_generation_usage

    def _capture_reserve(*a, **kw):
        captured["max_tokens"] = kw.get("max_tokens")
        return real_reserve(*a, **kw)

    monkeypatch.setattr(kayitmod, "generate_kayit_envanter_stream", _fake_stream)
    monkeypatch.setattr(kayitmod, "reserve_generation_usage", _capture_reserve)
    cid = _make_client(db_session)
    _put_inventory(db_session, cid)

    resp = _generate(db_session, cid)
    _consume(resp)

    assert captured["max_tokens"] == 32000


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
