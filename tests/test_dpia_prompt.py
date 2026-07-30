from legal_core.models import ClientProfile, ProcessRecord
from legal_core.prompt import build_dpia_envanter_prompt


def _rec():
    return ProcessRecord(departman="IK", is_sureci="Ozluk", alt_surec="Bordro",
                         kisi_grubu="Calisan", kategoriler=["Saglik Bilgileri"],
                         amaclar=["Bordro"], hukuki_sebepler=["m.6/3"], saklama_sureleri=["10 yil"])


def test_dpia_prompt_has_eight_sections_and_rubric():
    p = build_dpia_envanter_prompt([_rec()], ClientProfile(ad="X A.S."), ["Sifreleme"],
                                   ["Kural 1"], ["ozel_nitelikli", "savunmasiz_grup"])
    assert "Risk Matrisi" in p
    assert "Sonuç Kararı" in p
    for section in ("Proje ve Kapsam", "İşlemenin Tanımı", "Veri Akış",
                    "Uyum Değerlendirmesi", "Risk Azaltma", "Güncelleme"):
        assert section in p
    # Tetiklenen kriterler + rubrik + uydurma yasagi
    assert "ozel_nitelikli" in p and "savunmasiz_grup" in p
    assert "1-5" in p or "Olasılık" in p
    assert "UYDURMA" in p.upper() or "uydurma" in p


def test_dpia_prompt_empty_inventory_note():
    p = build_dpia_envanter_prompt([], ClientProfile(ad="X"), [], [], [])
    assert "süreç yok" in p.lower() or "envanterde" in p.lower()
