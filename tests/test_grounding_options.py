# tests/test_grounding_options.py
from app.grounding_options import OZEL_NITELIKLI, grounding_options


def test_ozel_nitelikli_etiketleri_katalogda_var():
    """Drift koruması: kategori adi degisirse KVKK m.6 uyarisi sessizce kaybolmasin."""
    kategoriler = set(grounding_options()["kategoriler"])
    eksik = OZEL_NITELIKLI - kategoriler
    assert not eksik, f"Ozel nitelikli etiket katalogda yok (m.6 uyarisi kirilir): {eksik}"


def test_m6_turlerinin_tamami_kapsanir():
    """KVKK m.6/1'in saydigi 12 tur de kapsanmali."""
    assert len(OZEL_NITELIKLI) == 12
    for beklenen in ("Sağlık Bilgileri", "Biyometrik Veri", "Genetik Veri", "Cinsel Hayat"):
        assert beklenen in OZEL_NITELIKLI


def test_endpoint_ozel_nitelikli_dondurur(client_fresh):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Büro"})
    body = client_fresh.get("/api/grounding/options").json()
    assert "Sağlık Bilgileri" in body["ozelNitelikli"]
    assert set(body["ozelNitelikli"]) <= set(body["kategoriler"])
