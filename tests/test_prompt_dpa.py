from legal_core.dpa_scope import DpaScope
from legal_core.models import ClientProfile, ProcessorInfo, ProcessRecord
from legal_core.prompt import build_dpa_envanter_prompt


def _rec(**kw):
    base = dict(departman="İK", is_sureci="Bordro", alt_surec="Maaş", kisi_grubu="Çalışan",
                aktarim=["Bulut"], kategoriler=["Kimlik"], teknik_tedbirler=["Şifreleme"])
    base.update(kw)
    return ProcessRecord(**base)


def _scope(recs):
    return DpaScope(eslesen_surecler=recs, kategoriler=["Kimlik"], veri_turleri=[],
                    amaclar=["Bordro"], saklama_sureleri=["10 yıl"],
                    teknik_tedbirler=["Şifreleme"], idari_tedbirler=[])


_PROFILE = ClientProfile(ad="Acme", unvan="Acme A.Ş.")


def test_prompt_has_15_section_skeleton_and_parties():
    proc = ProcessorInfo(ad="Bulut", unvan="Bulut A.Ş.", adres="İstanbul")
    p = build_dpa_envanter_prompt(_scope([_rec()]), _PROFILE, proc, ["Şifreleme"], [])
    for baslik in ["1. Taraflar", "8. Veri Güvenliği", "14. Sözleşmenin Sona Ermesi", "15. Muhtelif"]:
        assert baslik in p
    assert "Bulut A.Ş." in p          # işleyen unvanı
    assert "Acme A.Ş." in p           # veri sorumlusu
    assert "m.12" in p


def test_conditional_altisleyen_and_yurtdisi_off_by_default():
    proc = ProcessorInfo(ad="Bulut", unvan="Bulut A.Ş.")  # yurt_disi=False, alt_isleyen_var=False
    p = build_dpa_envanter_prompt(_scope([_rec()]), _PROFILE, proc, [], [])
    assert "7. Alt Veri İşleyen" not in p
    assert "12. Yurt Dışı Aktarım" not in p


def test_conditional_altisleyen_and_yurtdisi_on():
    proc = ProcessorInfo(ad="Bulut", unvan="Bulut A.Ş.", yurt_disi=True, alt_isleyen_var=True)
    p = build_dpa_envanter_prompt(_scope([_rec()]), _PROFILE, proc, [], [])
    assert "7. Alt Veri İşleyen" in p
    assert "12. Yurt Dışı Aktarım" in p
    assert "m.9" in p


def test_placeholder_instruction_present():
    proc = ProcessorInfo(ad="Bulut", unvan="Bulut A.Ş.")
    p = build_dpa_envanter_prompt(_scope([_rec()]), _PROFILE, proc, [], [])
    assert "UYDURMA" in p
