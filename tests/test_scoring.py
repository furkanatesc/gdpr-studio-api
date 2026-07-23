from legal_core.aggregate_sections import Section
from legal_core.scoring import cerez_completeness_score, completeness_score


def _full_section():
    return Section(
        is_sureci="A", kisi_gruplari=["Calisan"], kategoriler=["Kimlik"], veri_turleri=["Ad"],
        amaclar=["Bordro"], hukuki_sebepler=["m.5/2-c"], saklama_sureleri=["10 yil"],
        aktarim=["SGK"], toplama=["Form"],
    )


def test_completeness_full_section_is_one():
    assert completeness_score([_full_section()]) == 1.0


def test_completeness_empty_list_is_none():
    assert completeness_score([]) is None


def test_completeness_partial_counts_filled_slots():
    # 6 slottan 3 dolu (veri+amac+saklama), aktarim/toplama/hukuki bos -> 3/6
    s = Section(is_sureci="A", kategoriler=["Kimlik"], amaclar=["X"], saklama_sureleri=["5 yil"])
    assert completeness_score([s]) == 0.5


def test_completeness_veri_slot_ya_kategori_ya_veri_turu():
    s = Section(is_sureci="A", veri_turleri=["Ad"])  # yalniz veri slotu dolu
    assert completeness_score([s]) == 1 / 6


def test_completeness_averages_across_sections():
    full = _full_section()
    empty = Section(is_sureci="B")  # 0/6
    assert completeness_score([full, empty]) == 0.5  # (6+0)/12


def test_cerez_completeness_full_is_one():
    assert cerez_completeness_score(True, ["Zorunlu"], "GA", "var-kendi") == 1.0


def test_cerez_completeness_cmp_yok_ve_bos_dusuk():
    # kimlik var (1) + kategori/araç boş + cmp=yok -> 1/4
    assert cerez_completeness_score(True, [], "", "yok") == 0.25


def test_cerez_completeness_cmp_bos_string_eksik_sayilir():
    assert cerez_completeness_score(True, ["Analitik"], "Meta", "") == 0.75


def test_cerez_completeness_kimliksiz():
    assert cerez_completeness_score(False, ["Zorunlu"], "GA", "var-kendi") == 0.75


def test_cerez_completeness_tools_bosluk_bos_sayilir():
    assert cerez_completeness_score(True, ["Zorunlu"], "   ", "var-kendi") == 0.75
