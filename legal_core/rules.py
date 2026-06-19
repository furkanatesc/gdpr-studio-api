"""Hukuki iş kuralları — global (her dokümanda) + doküman türüne özel.

GLOBAL_RULES worker.py'den birebir taşındı (kod düzeyinde garanti). Doküman
türüne özel kurallar enjekte edilen BusinessRuleRepository'den gelir (Electron'da
is_kurallari SQLite tablosu; web'de Postgres).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

# Üretilen tüm dokümanlarda istisnasız uygulanan çekirdek hukuki kurallar.
# (privacy-legal-kvkk-2 / CLAUDE.md + hooks.json playbook'undan türetilmiştir.)
GLOBAL_RULES: list[str] = [
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


@runtime_checkable
class BusinessRuleRepository(Protocol):
    """Doküman türüne özel + genel ('Tümü') iş kurallarını döndürür."""

    def business_rules(self, doc_type: str) -> list[str]: ...
