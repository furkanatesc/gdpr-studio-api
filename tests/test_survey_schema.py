# tests/test_survey_schema.py
from app.survey_schema import load_survey_schema


def test_departmanlar_13_adet_ve_sekil_dogru():
    schema = load_survey_schema()
    departments = schema["departments"]
    assert len(departments) == 13
    for dept in departments:
        assert "key" in dept
        assert "label" in dept
        assert "bolumler" in dept
        for bolum in dept["bolumler"]:
            assert "label" in bolum
            assert "sorular" in bolum


def test_en_az_bir_bolumun_sorulari_bos_degil():
    schema = load_survey_schema()
    assert any(
        bolum["sorular"]
        for dept in schema["departments"]
        for bolum in dept["bolumler"]
    )


def test_vocab_dort_anahtar_ve_beklenen_sayilar():
    vocab = load_survey_schema()["vocab"]
    assert set(vocab.keys()) == {"kisiGrubu", "hukukiSebep", "kaynak", "yurtdisi"}
    assert len(vocab["kisiGrubu"]) >= 15
    assert len(vocab["hukukiSebep"]) >= 10
    assert len(vocab["kaynak"]) >= 6
    assert vocab["yurtdisi"] == ["Evet", "Hayır", "Muhtemel (bulut)", "Bilinmiyor"]


def test_ik_departmaninda_ise_alim_bolumu_var():
    schema = load_survey_schema()
    ik = next(
        d for d in schema["departments"]
        if d["key"].startswith("02-") or d["label"] == "İnsan Kaynakları"
    )
    assert any(b["label"] == "İşe Alım" for b in ik["bolumler"])


def test_hukuki_sebep_acik_riza_ile_baslayan_deger_icerir():
    hukuki = load_survey_schema()["vocab"]["hukukiSebep"]
    assert any(v.startswith("5/1 Açık Rıza") for v in hukuki)


def test_endpoint_survey_schema_dondurur(client_fresh):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Büro"})
    body = client_fresh.get("/api/inventory/survey-schema").json()
    assert len(body["departments"]) == 13
    assert "kisiGrubu" in body["vocab"]
