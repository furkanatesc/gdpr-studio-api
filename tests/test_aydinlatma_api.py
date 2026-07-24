# tests/test_aydinlatma_api.py
"""Aydinlatma uretim uclari: prepare / generate (SSE) / docx (T6)."""

from __future__ import annotations

import asyncio
import io
import uuid
import zipfile

import app.config as config_module
import app.idempotency as idem
import app.modules.aydinlatma as aydmod
import app.redis_client as rc
from app.auth.identity import Identity
from app.models import GeneratedDocument
from app.repositories import ClientRepository, GeneratedDocumentRepository
from legal_core.models import DocType

IDENT = Identity(
    user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
    org_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
    role="yonetici",
    email="dev@kvkkyonetim.local",
)

ROWS = [
    {"departman": "IK", "is_sureci": "Ozluk", "alt_surec": "Bordro", "kisi_grubu": "Calisan",
     "kategoriler": ["Kimlik", "Finans"], "amaclar": ["Bordro"], "saklama_sureleri": ["10 yil"]},
]


def _bootstrap_client(client_fresh, sector="otel"):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Buro"})
    return client_fresh.post("/api/clients", json={"name": "Otel A.S.", "sector": sector}).json()["id"]


def _put_inventory(client_fresh, cid, rows):
    r = client_fresh.put(f"/api/clients/{cid}/inventory", json={"rows": rows})
    assert r.status_code == 200, r.text


# ---- prepare -----------------------------------------------------------

def test_prepare_musvekkil_yok_404(client_fresh):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Buro"})
    r = client_fresh.post(
        "/api/clients/00000000-0000-0000-0000-000000000099/aydinlatma/prepare",
        json={"targetGroups": ["Calisan"]},
    )
    assert r.status_code == 404


def test_prepare_hedef_grupta_satir_yok_422(client_fresh):
    cid = _bootstrap_client(client_fresh)
    _put_inventory(client_fresh, cid, ROWS)
    r = client_fresh.post(f"/api/clients/{cid}/aydinlatma/prepare", json={"targetGroups": ["Ziyaretci"]})
    assert r.status_code == 422


def test_prepare_eslesen_envanter_200(client_fresh):
    cid = _bootstrap_client(client_fresh)
    _put_inventory(client_fresh, cid, ROWS)
    r = client_fresh.post(f"/api/clients/{cid}/aydinlatma/prepare", json={"targetGroups": ["Calisan"]})
    assert r.status_code == 200, r.text
    sections = r.json()["sections"]
    assert len(sections) == 1
    s = sections[0]
    assert s["isSureci"] == "Bordro"  # bolum etiketi = alt_surec (yoksa is_sureci)
    assert s["kategoriler"] == ["Kimlik", "Finans"]
    assert s["amaclar"] == ["Bordro"]
    assert "oneriler" in s


def test_prepare_gurultulu_veri_turu_kanoniklesir(client_fresh):
    """veri_turleri'nde gurultulu varyant ('AD-SOYAD') gercek kanonik forma donmeli.

    data/canonical/veri_turleri.json'da kanonik deger "Ad-soyad"; envanterdeki
    ham deger buyuk harfli ama norm-exact eslesir (norm("AD-SOYAD")==norm("Ad-soyad")).
    """
    cid = _bootstrap_client(client_fresh)
    _put_inventory(
        client_fresh,
        cid,
        [
            {
                "departman": "IK", "is_sureci": "Ozluk", "kisi_grubu": "Calisan",
                "kategoriler": ["Kimlik"], "veri_turleri": ["AD-SOYAD"],
            }
        ],
    )
    r = client_fresh.post(f"/api/clients/{cid}/aydinlatma/prepare", json={"targetGroups": ["Calisan"]})
    assert r.status_code == 200, r.text
    s = r.json()["sections"][0]
    assert s["veriTurleri"] == ["Ad-soyad"]


# ---- generate (SSE) — dogrudan cagri (Depends cozulmez) ----------------

def _managed_billing_settings():
    config_module._settings = config_module.Settings(
        _env_file=None,
        managed_anthropic_api_key="sk-managed-test",
        allowed_origins="http://localhost:3000",
        redis_url="",
        stripe_secret_key="sk_test_x",
        stripe_webhook_secret="whsec_x",
    )
    return config_module._settings


def _make_client(db_session):
    c = ClientRepository(db_session).create(IDENT.org_id, "Otel", "otel")
    db_session.commit()
    return c.id


def _fake_stream(*a, **k):
    yield "grounding", []
    yield "delta", "Aydinlatma"
    yield "delta", " metni"
    yield "done", {"model": "claude-x", "usage": {"inputTokens": 10, "outputTokens": 20}}


def _consume(response) -> str:
    async def _run():
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        return chunks

    return "".join(asyncio.run(_run()))


def _generate(db_session, client_id, **overrides):
    body = aydmod.GenerateIn(sections=[aydmod.SectionIn(is_sureci="Ozluk", kategoriler=["Kimlik"])])
    kwargs = dict(session=db_session, identity=IDENT, x_anthropic_key=None, idempotency_key=None)
    kwargs.update(overrides)
    return aydmod.generate(client_id=client_id, body=body, **kwargs)


def test_generate_musvekkil_yok_404(db_session, monkeypatch):
    _managed_billing_settings()
    monkeypatch.setattr(aydmod, "generate_aydinlatma_envanter_stream", _fake_stream)
    from fastapi import HTTPException

    try:
        _generate(db_session, uuid.uuid4())
    except HTTPException as e:
        assert e.status_code == 404
    else:
        raise AssertionError("404 bekleniyordu")


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


def test_generate_gecersiz_client_404_idempotency_kilidi_almaz(client, db_session, monkeypatch):
    """404 (sahiplik), idempotency claim'inden ÖNCE olmalı: kilit hiç alınmamamış olmalı.

    Geçersiz client_id + bir Idempotency-Key ile 404 alan istek kilidi almamalı; aynı
    anahtarla ARDINDAN gelen GEÇERLİ client_id isteği sahte 409 almamalı.
    """
    config_module._settings = config_module.Settings(
        _env_file=None,
        managed_anthropic_api_key="sk-managed-test",
        allowed_origins="http://localhost:3000",
        redis_url="",
    )
    _use_fake_redis(monkeypatch)
    monkeypatch.setattr(aydmod, "generate_aydinlatma_envanter_stream", _fake_stream)

    cid = _make_client(db_session)
    body = {"sections": [{"isSureci": "Ozluk", "kategoriler": ["Kimlik"]}]}
    headers = {"Idempotency-Key": "aydinlatma-404-key"}

    r1 = client.post(
        "/api/clients/00000000-0000-0000-0000-000000000099/aydinlatma/generate",
        json=body,
        headers=headers,
    )
    assert r1.status_code == 404

    with client.stream(
        "POST", f"/api/clients/{cid}/aydinlatma/generate", json=body, headers=headers
    ) as r2:
        assert r2.status_code != 409
        "".join(r2.iter_text())


def test_generate_olay_sirasi_ve_uyum_kaydi(db_session, monkeypatch):
    _managed_billing_settings()
    monkeypatch.setattr(aydmod, "generate_aydinlatma_envanter_stream", _fake_stream)
    cid = _make_client(db_session)

    resp = _generate(db_session, cid)
    body = _consume(resp)

    assert "event: grounding" in body
    assert body.index("event: grounding") < body.index("event: delta") < body.index("event: done")
    assert "Bu çıktı avukat" in body or "metni" in body  # delta metni akmis

    rows = db_session.query(GeneratedDocument).filter_by(doc_type="aydinlatma").all()
    assert len(rows) == 1
    assert str(rows[0].org_id) == str(IDENT.org_id)


def _fake_stream_truncated(*a, **k):
    yield "grounding", []
    yield "delta", "Kesik aydinlatma metni..."
    yield "done", {
        "model": "claude-x",
        "usage": {"inputTokens": 8000, "outputTokens": 8000},
        "stopReason": "max_tokens",
    }


def test_generate_max_tokensta_saklanmaz_ve_uyari_yayinlanir(db_session, monkeypatch):
    """Borc: kesik uretim (stop_reason=max_tokens) SAKLANMAMALI, istemci 'warning' alir."""
    from app.models import ClientDocument

    _managed_billing_settings()
    monkeypatch.setattr(aydmod, "generate_aydinlatma_envanter_stream", _fake_stream_truncated)
    cid = _make_client(db_session)

    resp = _generate(db_session, cid)
    body = _consume(resp)

    assert "event: warning" in body
    assert "event: error" not in body
    rows = db_session.query(ClientDocument).filter_by(client_id=cid).all()
    assert len(rows) == 0


def test_generate_uyari_donedan_once_gelir(db_session, monkeypatch):
    """Borc #1: 'warning' 'done'dan ONCE gelmeli — done'u terminal sayan bir tuketici
    uyariyi kacirmamali; done payload'i da ek sigorta olarak 'incomplete' isaretlenmeli."""
    import json

    _managed_billing_settings()
    monkeypatch.setattr(aydmod, "generate_aydinlatma_envanter_stream", _fake_stream_truncated)
    cid = _make_client(db_session)

    resp = _generate(db_session, cid)
    body = _consume(resp)

    assert "event: warning" in body and "event: done" in body
    assert body.index("event: warning") < body.index("event: done")

    done_line = [ln for ln in body.splitlines() if ln.startswith("data: ")][-1]
    done_payload = json.loads(done_line[len("data: "):])
    assert done_payload["incomplete"] is True
    assert done_payload["warningMessage"]


def test_generate_max_tokensta_uyum_kaydi_geri_alinir(db_session, monkeypatch):
    """Borc #2: kesmede generated_documents satiri SAYILMAMALI; org'un ONCEKI gecerli
    kaydi ETKILENMEMELI (yalniz bu kosuya ait satir silinir)."""
    _managed_billing_settings()
    GeneratedDocumentRepository(db_session).record(IDENT.org_id, DocType.aydinlatma)
    db_session.commit()

    monkeypatch.setattr(aydmod, "generate_aydinlatma_envanter_stream", _fake_stream_truncated)
    cid = _make_client(db_session)

    resp = _generate(db_session, cid)
    _consume(resp)

    rows = db_session.query(GeneratedDocument).filter_by(doc_type="aydinlatma").all()
    assert len(rows) == 1  # yalniz onceki gecerli kayit kaldi


def _fake_stream_with_stop_reason(stop_reason):
    def _f(*a, **k):
        yield "grounding", []
        yield "delta", "Aydinlatma metni"
        yield "done", {
            "model": "claude-x",
            "usage": {"inputTokens": 10, "outputTokens": 20},
            "stopReason": stop_reason,
        }

    return _f


def test_generate_baglam_penceresi_asildiginda_saklanmaz(db_session, monkeypatch):
    """Borc #3: yalniz max_tokens degil, model_context_window_exceeded da kesme sayilmali."""
    from app.models import ClientDocument

    _managed_billing_settings()
    monkeypatch.setattr(
        aydmod, "generate_aydinlatma_envanter_stream",
        _fake_stream_with_stop_reason("model_context_window_exceeded"),
    )
    cid = _make_client(db_session)

    resp = _generate(db_session, cid)
    body = _consume(resp)

    assert "event: warning" in body
    assert db_session.query(ClientDocument).filter_by(client_id=cid).count() == 0
    assert db_session.query(GeneratedDocument).filter_by(doc_type="aydinlatma").count() == 0


def test_generate_refusal_saklanmaz_ve_farkli_mesaj_gosterilir(db_session, monkeypatch):
    """Borc #3: refusal da SAKLANMAZ ama mesaji uzunluk-kesme mesajindan FARKLI olmali."""
    from app.models import ClientDocument

    _managed_billing_settings()
    monkeypatch.setattr(
        aydmod, "generate_aydinlatma_envanter_stream",
        _fake_stream_with_stop_reason("refusal"),
    )
    cid = _make_client(db_session)

    resp = _generate(db_session, cid)
    body = _consume(resp)

    assert "event: warning" in body
    assert "generation_refused" in body
    assert "truncated_output_limit" not in body
    assert db_session.query(ClientDocument).filter_by(client_id=cid).count() == 0
    assert db_session.query(GeneratedDocument).filter_by(doc_type="aydinlatma").count() == 0


def test_generate_end_turn_saklanir_regresyon_kilidi(db_session, monkeypatch):
    """Regresyon kilidi: stopReason='end_turn' -> belge HALA saklanir (davranis birebir)."""
    from app.models import ClientDocument

    _managed_billing_settings()
    monkeypatch.setattr(
        aydmod, "generate_aydinlatma_envanter_stream",
        _fake_stream_with_stop_reason("end_turn"),
    )
    cid = _make_client(db_session)

    resp = _generate(db_session, cid)
    body = _consume(resp)

    assert "event: warning" not in body
    rows = db_session.query(ClientDocument).filter_by(client_id=cid).all()
    assert len(rows) == 1
    assert db_session.query(GeneratedDocument).filter_by(doc_type="aydinlatma").count() == 1


def test_generate_kesmede_idempotency_kilidi_birakilir(db_session, monkeypatch):
    """Borc #4: kesmede idempotency kilidi BIRAKILMALI — uyaridaki 'yeniden deneyin'
    tavsiyesine uyan istemci 409 almamali."""
    _managed_billing_settings()
    fake = _use_fake_redis(monkeypatch)
    monkeypatch.setattr(aydmod, "generate_aydinlatma_envanter_stream", _fake_stream_truncated)
    cid = _make_client(db_session)

    resp = _generate(db_session, cid, idempotency_key="ayd-kesme-1")
    _consume(resp)

    assert fake.store == {}


def test_generate_belgeyi_saklar_iki_puanla(db_session, monkeypatch):
    from app.models import ClientDocument

    _managed_billing_settings()
    monkeypatch.setattr(aydmod, "generate_aydinlatma_envanter_stream", _fake_stream)
    cid = _make_client(db_session)

    resp = _generate(db_session, cid)
    _consume(resp)  # 'done' tetiklenir -> best-effort saklama + commit

    rows = db_session.query(ClientDocument).filter_by(client_id=cid).all()
    assert len(rows) == 1
    assert "metni" in rows[0].content          # _fake_stream delta metni
    assert rows[0].doc_type == "aydinlatma"
    assert rows[0].title == "Genel"            # SectionIn kisi_gruplari bos -> Genel
    assert rows[0].score_completeness is not None   # kategoriler dolu -> >0
    assert rows[0].score_compliance == 0.0     # org'da hic uyum statusu yok -> 0/6


# ---- docx ----------------------------------------------------------------

def test_docx_musvekkil_yok_404(client_fresh):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Buro"})
    r = client_fresh.post(
        "/api/clients/00000000-0000-0000-0000-000000000099/aydinlatma/docx",
        json={"text": "metin"},
    )
    assert r.status_code == 404


def test_docx_uretir(client_fresh):
    cid = _bootstrap_client(client_fresh)
    r = client_fresh.post(
        f"/api/clients/{cid}/aydinlatma/docx",
        json={"text": "# Baslik\nIcerik satiri.", "title": "Test Belgesi"},
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert "attachment" in r.headers["content-disposition"]
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert "word/document.xml" in zf.namelist()
