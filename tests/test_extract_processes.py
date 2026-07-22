from scripts.extract_processes.aggregate import aggregate_processes
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


def test_canonical_kisi_grubu_merges_case_variant():
    """Gerçek veride aynı grup baş harfi küçük yazılmış bulundu (1x) → büyük-harfli forma katıl."""
    assert canonical_kisi_grubu("evrakta Yer Alan 3. Kişi") == "Evrakta Yer Alan 3. Kişi"


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


def test_row_to_process_narrative_fields_not_split_on_comma():
    """Hukuki sebep/saklama/amaç/dayanak/tedbir gibi cümleli alanlarda virgül cümle-içi
    noktalamadır; ayraç DEĞİLDİR (PROGSA kıyas Bulgu 3). Token alanlar (veri türü) böler."""
    header = [
        "Veri Konusu Kişi Grubu", "Hukuki Sebep", "Veri Kullanım Amacı",
        "Azami Süre (Saklama)", "İdari Güvenlik Tedbiri", "Veri Türü",
    ]
    cells = [
        "Çalışan",
        "5/2e Bir hakkın tesisi, kullanılması, korunması",
        "İş Faaliyetlerinin Yürütülmesi / Denetimi",
        "Sözleşme sona erdikten sonra 10 yıl, mevzuat gereği saklanır",
        "Erişim yetkilendirme, loglama ve şifreleme uygulanır",
        "Ad, Soyad, Mail",
    ]
    rec = row_to_process(header, cells)
    assert rec["hukuki_sebepler"] == ["5/2e Bir hakkın tesisi, kullanılması, korunması"]
    assert rec["amaclar"] == ["İş Faaliyetlerinin Yürütülmesi / Denetimi"]
    assert rec["saklama_sureleri"] == ["Sözleşme sona erdikten sonra 10 yıl, mevzuat gereği saklanır"]
    assert rec["idari_tedbirler"] == ["Erişim yetkilendirme, loglama ve şifreleme uygulanır"]
    # Token alan: virgülle bölme KORUNUR
    assert rec["veri_turleri"] == ["Ad", "Soyad", "Mail"]


def test_row_to_process_narrative_fields_still_split_on_semicolon():
    """Narrative alanda gerçek çoklu değer noktalı virgül/satır sonuyla ayrılır — bunlar böler."""
    header = ["Veri Konusu Kişi Grubu", "Hukuki Sebep"]
    cells = ["Çalışan", "5/2c Sözleşmenin ifası; 5/2e Bir hakkın tesisi, kullanılması"]
    rec = row_to_process(header, cells)
    assert rec["hukuki_sebepler"] == [
        "5/2c Sözleşmenin ifası",
        "5/2e Bir hakkın tesisi, kullanılması",
    ]


def _row(**kw):
    base = {
        "departman": "İK", "is_sureci": "İşe Alım", "alt_surec": "Başvuru", "kisi_grubu": "Çalışan Adayı",
        "kategoriler": [], "veri_turleri": [], "hukuki_sebepler": [], "saklama_sureleri": [],
    }
    base.update(kw)
    return base


def test_aggregate_collapses_rows_into_one_process():
    """Aynı (departman, is_sureci, alt_surec, kisi_grubu) → TEK süreç; alanlar birleşir."""
    rows = [
        _row(kategoriler=["Kimlik"], veri_turleri=["Ad"], saklama_sureleri=["1 yıl"]),
        _row(kategoriler=["Kimlik"], veri_turleri=["Soyad"], saklama_sureleri=["1 yıl"]),
        _row(kategoriler=["İletişim"], veri_turleri=["E-posta"]),
    ]
    got = aggregate_processes(rows, sector="sirket")
    assert len(got) == 1  # 3 satır → 1 süreç
    p = got[0]
    assert p["sector"] == "sirket"
    assert p["kisi_grubu"] == "Çalışan Adayı"
    assert p["data"]["kategoriler"] == ["Kimlik", "İletişim"]
    assert p["data"]["veri_turleri"] == ["Ad", "Soyad", "E-posta"]
    assert p["data"]["saklama_sureleri"] == ["1 yıl"]  # dedupe


def test_aggregate_separates_different_kisi_grubu():
    """Aynı süreç, farklı kişi grubu → AYRI kayıt (sorgu ekseni)."""
    rows = [_row(kisi_grubu="Çalışan"), _row(kisi_grubu="Çalışan Adayı")]
    got = aggregate_processes(rows, sector="sirket")
    assert len(got) == 2
    assert {p["kisi_grubu"] for p in got} == {"Çalışan", "Çalışan Adayı"}


def test_aggregate_empty_stays_empty():
    """Uydurma yok: kaynak boşsa alan boş kalır."""
    got = aggregate_processes([_row()], sector="otel")
    assert got[0]["data"]["saklama_sureleri"] == []
    assert got[0]["data"]["idari_tedbirler"] == []


def test_aggregate_is_order_stable():
    rows = [_row(alt_surec="B"), _row(alt_surec="A")]
    got = aggregate_processes(rows, sector="otel")
    assert [p["alt_surec"] for p in got] == ["A", "B"]  # departman,is_sureci,alt_surec sirali
