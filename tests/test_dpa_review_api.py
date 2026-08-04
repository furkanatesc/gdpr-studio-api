from __future__ import annotations

import io
import uuid

import pytest
from docx import Document

from legal_core.dpa_review import DPA_CHECKLIST, DpaReviewResult, ReviewFinding


# --- test_dpa_api.py ile aynı yardımcılar ---
def _bootstrap_client(client_fresh, sector="saglik"):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Buro"})
    return client_fresh.post("/api/clients", json={"name": "Klinik A.S.", "sector": sector}).json()["id"]


def _put_inv(client_fresh, cid, rows):
    assert client_fresh.put(f"/api/clients/{cid}/inventory", json={"rows": rows}).status_code == 200


ROW = {"departman": "IK", "is_sureci": "Ozluk", "alt_surec": "Bordro", "kisi_grubu": "Calisan",
       "kategoriler": ["Sağlık Bilgileri"], "amaclar": ["Bordro"], "saklama_sureleri": ["10 yil"],
       "aktarim": ["Bulut"]}


def _create_processor(client_fresh, cid, aktarim_aliases=("Bulut",)):
    r = client_fresh.post(f"/api/clients/{cid}/processors",
                          json={"ad": "Bulut", "unvan": "Bulut A.Ş.", "aktarimAliases": list(aktarim_aliases)})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _docx_bytes(text: str) -> bytes:
    doc = Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _fixed_result() -> DpaReviewResult:
    bulgular = [ReviewFinding(it.id, "var", "alıntı", "gerekçe", "") for it in DPA_CHECKLIST]
    return DpaReviewResult(bulgular=bulgular, uygun=11, eksik=0, yetersiz=0,
                           kirmizi_bayrak=0, disclaimer="AI taslağı.")


@pytest.fixture
def _patch_review(monkeypatch):
    import app.modules.dpa as dpa_mod
    monkeypatch.setattr(dpa_mod, "review_dpa", lambda *a, **k: _fixed_result())


_BYOK = {"X-Anthropic-Key": "test-key"}


def test_review_requires_text_or_file(client_fresh, _patch_review):
    cid = _bootstrap_client(client_fresh)
    r = client_fresh.post(f"/api/clients/{cid}/dpa/review", data={}, headers=_BYOK)
    assert r.status_code == 422


def test_review_happy_path_text(client_fresh, _patch_review):
    cid = _bootstrap_client(client_fresh)
    _put_inv(client_fresh, cid, [ROW])
    r = client_fresh.post(f"/api/clients/{cid}/dpa/review",
                          data={"text": "Örnek DPA: gizlilik ve tedbirler..."}, headers=_BYOK)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["bulgular"]) == 11
    assert {"uygun", "eksik", "yetersiz", "kirmiziBayrak", "disclaimer"} <= set(body)
    assert body["bulgular"][0]["baslik"]  # checklist zenginleştirme
    assert "kvkkRef" in body["bulgular"][0]


def test_review_docx_upload(client_fresh, _patch_review):
    cid = _bootstrap_client(client_fresh)
    _put_inv(client_fresh, cid, [ROW])
    r = client_fresh.post(
        f"/api/clients/{cid}/dpa/review",
        files={"file": ("dpa.docx", _docx_bytes("gizlilik taahhüdü madde 5"),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        headers=_BYOK,
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["bulgular"]) == 11


def test_review_empty_docx_422(client_fresh, _patch_review):
    cid = _bootstrap_client(client_fresh)
    r = client_fresh.post(
        f"/api/clients/{cid}/dpa/review",
        files={"file": ("bos.docx", _docx_bytes(""),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        headers=_BYOK,
    )
    assert r.status_code == 422


def test_review_unsupported_extension_422(client_fresh, _patch_review):
    cid = _bootstrap_client(client_fresh)
    r = client_fresh.post(f"/api/clients/{cid}/dpa/review",
                          files={"file": ("dpa.txt", b"metin", "text/plain")}, headers=_BYOK)
    assert r.status_code == 422


def test_review_unknown_client_404(client_fresh, _patch_review):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Buro"})
    r = client_fresh.post(f"/api/clients/{uuid.uuid4()}/dpa/review",
                          data={"text": "metin"}, headers=_BYOK)
    assert r.status_code == 404
