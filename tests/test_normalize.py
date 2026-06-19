import unicodedata

from legal_core.normalize import norm


def test_bos_ve_none():
    assert norm("") == ""
    assert norm(None) == ""
    assert norm(0) == ""


def test_turkce_I_katlamasi():
    # Türkçe I/ı belirsizliği: "IP" (İng. kısaltma) ile "ip" eşleşmeli.
    assert norm("IP") == norm("ip") == "ip"
    # İ büyük harfi i'ye katlanır (ş gibi diğer harfler korunur).
    assert norm("İletişim") == norm("iletişim") == "iletişim"


def test_nfc_decomposed_esitligi():
    # NFD (decomposed) ve NFC (composed) aynı normalize sonucunu vermeli.
    nfc = "Sağlık Bilgileri"
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfc != nfd  # ham string'ler farklı
    assert norm(nfc) == norm(nfd)  # normalize sonrası aynı


def test_kucuk_harf_ve_kirpma():
    assert norm("  E-Posta  ") == "e-posta"
