"""Kuratorlu synonym seti: 13 onaylı (ham, kanonik, field) eşlemesi.

Kaynak: sdd/synonym-brief.md — kullanıcı onaylı, elle doğrulanmış set.
"""

from __future__ import annotations

from legal_core.canonical import load_canonicalizer
from legal_core.normalize import norm

APPROVED = [
    ("Çalışan Aday İşlem", "Çalışan Adayı İşlem", "kategoriler"),
    ("Fiziksel Mekan Güvenliği", "Fiziksel Mekân Güvenliği", "kategoriler"),
    ("İşlemTarihi", "İşlem tarihi", "veri_turleri"),
    ("İşlem Tariihi", "İşlem tarihi", "veri_turleri"),
    ("Cinsiyeti", "Cinsiyet", "veri_turleri"),
    ("e- posta", "E-posta", "veri_turleri"),
    ("Mail Adresi", "E-posta", "veri_turleri"),
    ("Vergi Kimlik Numarası", "Vergi Kimlik Numarası (VKN)", "veri_turleri"),
    ("VKN", "Vergi Kimlik Numarası (VKN)", "veri_turleri"),
    ("Mesaj İçeriği", "Mesaj içerikleri", "veri_turleri"),
    ("Telefon Numarası (Mobil)", "Telefon numarası", "veri_turleri"),
    ("Engel Durumu", "Engellilik durumu", "veri_turleri"),
    ("TCKN", "T.C. kimlik no", "veri_turleri"),
    ("IBAN", "Banka hesap / IBAN bilgileri", "veri_turleri"),
]


def test_onayli_eslemeler_calisiyor():
    canon = load_canonicalizer()
    for ham, kanonik, field in APPROVED:
        assert canon.canonicalize(ham, field) == kanonik, f"{field}: {ham!r} -> {kanonik!r} basarisiz"


def test_synonym_yolu_gercekten_tetikleniyor():
    canon = load_canonicalizer()
    for ham, kanonik, field in APPROVED:
        assert norm(ham) != norm(kanonik), f"{ham!r} norm-exact ile zaten yakalaniyor (synonym no-op)"
        assert canon.canonicalize(ham, field) == kanonik


def test_hedefler_kanonik_listede():
    canon = load_canonicalizer()
    targets_by_field: dict[str, set[str]] = {}
    for _, kanonik, field in APPROVED:
        targets_by_field.setdefault(field, set()).add(kanonik)
    for field, targets in targets_by_field.items():
        norm_map = canon._norm_maps[field]
        for target in targets:
            assert norm(target) in norm_map, f"{field}: hedef {target!r} kanonik listede degil"


def test_elenen_yanlislar_ham_kalir():
    canon = load_canonicalizer()
    assert canon.canonicalize("Mal Bilgileri", "veri_turleri") == "Mal Bilgileri"
    assert canon.canonicalize("Teslimat Adresi", "veri_turleri") == "Teslimat Adresi"
