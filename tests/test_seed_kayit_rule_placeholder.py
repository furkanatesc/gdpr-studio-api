"""I1: kayit yolunda bos saklama suresi icin TEK placeholder dizesi kullanilmali.

Once ucfarkli talimat vardi: baslik '[Avukat tarafindan doldurulacak]', format_processes
'[envanterde belirtilmemis - UYDURMA]', seed kurali '[Avukat tarafindan belirlenecek]'.
Kayit yolunda (build_kayit_envanter_prompt + seed'deki kayit is kurali) ONAY_BEKLEYEN_PLACEHOLDER
ile ayni dizeye indirgenmeli ve 'bos birak' ifadesi kalkmali (bos birakma C1'i geri getirir).

Final incelemenin 2. turu ek bir catisma buldu: GLOBAL_RULES'daki #5 maddesi
('SAKLAMA SÜRESİ BOŞLUĞU') FARKLI bir placeholder ('[Saklama süresi avukat/veri sorumlusu
tarafından belirlenecek]') emrediyordu; kayit promptunun BIRLESTIRILMIS kural listesinde
bu, seed'in hizali kuraliyla YAN YANA duruyordu. Duzeltme: kayit yoluna GLOBAL_RULES'un
kendisi degil, kayit_aligned_global_rules() kopyasi veriliyor (yalniz #5 metni hizali);
GLOBAL_RULES canli /api/generate + /api/clients/{id}/cerez/generate icin degismeden kalir."""

from __future__ import annotations

from app.seed import RULES
from legal_core.models import ClientProfile
from legal_core.prompt import ONAY_BEKLEYEN_PLACEHOLDER, build_kayit_envanter_prompt
from legal_core.rules import GLOBAL_RULES, kayit_aligned_global_rules

# GLOBAL_RULES'un beklenen, HİÇ DEĞİŞMEMESİ gereken içeriği (BASE f9138f3 ile birebir).
_EXPECTED_GLOBAL_RULES = [
    "Dil ve üslup: Çıktı yalnızca Türkçe, kurumsal ve yapılandırılmış (başlık, madde, "
    "tablo) olmalıdır.",
    "Madde atfı zorunlu: Her hukuki değerlendirmede ilgili KVKK/GDPR maddesine doğrudan "
    "atıf yap (ör. KVKK m.5/2-ç, GDPR m.6/1-c).",
    "Hukuki dayanak hiyerarşisi: Öncelik açık rıza ve sözleşmenin ifasıdır; meşru menfaat "
    "(KVKK m.5/2-f) kullanılacaksa LİA (Meşru Menfaat Denge Testi) gerektiğini vurgula.",
    "DAYANAK UYDURMA YASAĞI: Hukuki sebebi, amacı veya saklama süresini kendin İCAT ETME. "
    "Yalnızca aşağıdaki envanter kayıtlarında verilen değerleri kullan.",
    "SAKLAMA SÜRESİ BOŞLUĞU: Envanterde saklama süresi verilmemişse süre UYDURMA; "
    "ilgili alana '[Saklama süresi avukat/veri sorumlusu tarafından belirlenecek]' yaz.",
    "ÖZEL NİTELİKLİ VERİ (KVKK m.6): Sağlık, biyometrik, genetik, ceza mahkûmiyeti gibi "
    "özel nitelikli veri işleniyorsa, bunun ancak açık rıza veya m.6'daki sınırlı "
    "istisnalarla işlenebileceğini açıkça belirt ve ek güvenlik tedbirlerini hatırlat.",
    "YURT DIŞI AKTARIM (KVKK m.9 / GDPR m.44-49): Aktarım varsa kullanılan mekanizmayı "
    "(Kurul kararı / taahhütname / SCCs / yeterlilik kararı / açık rıza) belirt; "
    "mekanizma belirsizse bunu eksiklik olarak işaretle.",
    "Risk derecelendirmesi: Risk değerlendirmesi içeren dokümanlarda 4'lü matris kullan: "
    "Kritik / Yüksek / Orta / Düşük.",
]

_ESKI_PLACEHOLDER_1 = "[Saklama süresi avukat/veri sorumlusu tarafından belirlenecek]"
_ESKI_PLACEHOLDER_2 = "[Avukat tarafından belirlenecek]"


def test_global_rules_degismedi():
    """GLOBAL_RULES canlı /api/generate + /api/clients/{id}/cerez/generate yollarında
    kullanılır — kayıt yolu düzeltmesi bu sabiti DEĞİŞTİRMEMELİ (byte-bir-byte aynı)."""
    assert GLOBAL_RULES == _EXPECTED_GLOBAL_RULES


def test_seed_kayit_kurali_placeholder_ile_ayni_dizeyi_kullanir():
    kayit_kurallari = [metin for tur, metin in RULES if tur == "kayit"]
    saklama_kurali = next(m for m in kayit_kurallari if "UYDURMA" in m)
    assert ONAY_BEKLEYEN_PLACEHOLDER in saklama_kurali
    assert "bos birak" not in saklama_kurali.lower()
    assert "boş bırak" not in saklama_kurali.lower()


def test_kayit_aligned_global_rules_sadece_saklama_maddesini_degistirir():
    """kayit_aligned_global_rules(), GLOBAL_RULES ile aynı uzunlukta olmalı ve yalnızca
    #5 (SAKLAMA SÜRESİ BOŞLUĞU) maddesi değişmeli — diğer 7 madde birebir korunmalı."""
    aligned = kayit_aligned_global_rules()
    assert len(aligned) == len(GLOBAL_RULES)
    farkli = [i for i, (a, b) in enumerate(zip(aligned, GLOBAL_RULES, strict=True)) if a != b]
    assert farkli == [4]
    assert ONAY_BEKLEYEN_PLACEHOLDER in aligned[4]
    assert _ESKI_PLACEHOLDER_1 not in aligned[4]


def test_kayit_promptu_birlestirilmis_kural_listesinde_tek_placeholder_kullanir():
    """Kayıt yolunun MODELE GERÇEKTEN verdiği birleştirilmiş kural listesinde (kayit_aligned_
    global_rules() + seed'deki 'Tümü'/'kayit' kuralları) saklama boşluğu için TEK placeholder
    dizesi kalmalı; eski iki varyanttan hiçbiri geçmemeli."""
    merged_rules = kayit_aligned_global_rules() + [
        metin for tur, metin in RULES if tur in ("Tümü", "kayit")
    ]
    profile = ClientProfile(ad="ACME A.S.", unvan="ACME Anonim Şirketi", adres="İstanbul")
    prompt = build_kayit_envanter_prompt(
        records=[], profile=profile, measures=[], rules=merged_rules,
    )
    kurallar_bolumu = prompt.split("## BAĞLAYICI İŞ KURALLARI (HARFİYEN UY)")[1]

    assert _ESKI_PLACEHOLDER_1 not in kurallar_bolumu
    assert _ESKI_PLACEHOLDER_2 not in kurallar_bolumu
    assert ONAY_BEKLEYEN_PLACEHOLDER in kurallar_bolumu
