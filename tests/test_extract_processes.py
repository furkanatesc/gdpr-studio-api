from scripts.extract_processes.mapping import (
    canonical_kisi_grubu,
    row_to_process,
    sector_for_filename,
)


def test_sector_for_filename():
    assert sector_for_filename("X DİŞ KLİNİĞİ Kişisel Veri İşleme Envanteri .xlsx") == "dis_klinigi"
    assert sector_for_filename("X OTELİ Kişisel Veri İşleme Envanteri .xlsx") == "otel"
    assert sector_for_filename("PROGSA Kişisel Veri İşleme Envanteri .xlsx") == "meslek_orgutu"
    assert sector_for_filename("bilinmeyen.xlsx") is None


def test_canonical_kisi_grubu_fixes_known_typo():
    assert canonical_kisi_grubu("Tederikçi Yetkilisi") == "Tedarikçi Yetkilisi"  # 8x yazım hatası
    assert canonical_kisi_grubu("  Çalışan ") == "Çalışan"


def test_canonical_kisi_grubu_drops_junk():
    assert canonical_kisi_grubu("Organizasyon Şirket Fiyat Teklifi") is None  # kişi grubu değil
    assert canonical_kisi_grubu("") is None
    assert canonical_kisi_grubu("???") is None


def test_row_to_process_maps_all_key_columns():
    header = [
        "Departman", "İş Süreci", "Alt Süreç", "Veri Konusu Kişi Grubu",
        "Kişisel Veri Kategorisi", "Veri Türü", "Hukuki Sebep", "Dayanak",
        "Azami Süre (Saklama)", "İşlem",
    ]
    cells = [
        "İNSAN KAYNAKLARI", "İşe Giriş İşlemleri", "Kimlik teyidi", "Çalışan",
        "Kimlik", "Ad, Soyad", "5/2ç Hukuki Yükümlülük", "4857 s. Kanun",
        "İşten ayrılıştan itibaren 10 yıl", "Elde Etme",
    ]
    rec = row_to_process(header, cells)
    assert rec["departman"] == "İNSAN KAYNAKLARI"
    assert rec["is_sureci"] == "İşe Giriş İşlemleri"
    assert rec["alt_surec"] == "Kimlik teyidi"
    assert rec["kisi_grubu"] == "Çalışan"
    assert rec["kategoriler"] == ["Kimlik"]
    assert rec["veri_turleri"] == ["Ad", "Soyad"]
    assert rec["hukuki_sebepler"] == ["5/2ç Hukuki Yükümlülük"]
    assert rec["saklama_sureleri"] == ["İşten ayrılıştan itibaren 10 yıl"]


def test_row_to_process_none_without_kisi_grubu():
    header = ["Departman", "İş Süreci", "Veri Konusu Kişi Grubu"]
    assert row_to_process(header, ["İK", "İşe Alım", ""]) is None
