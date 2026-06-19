"""Envanter grounding — kullanıcı etiketlerini gerçek KVKK kategorilerine eşler.

db_retriever'ın kategori-bazlı grounding mantığı buraya taşındı; veri kaynağı
artık enjekte edilen bir CategoryRepository (JSON, SQLite veya Postgres olabilir).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import InventoryRecord
from .normalize import norm

# Arayüzdeki kullanıcı dostu etiketler -> gerçek KVKK kategori adı.
# Yalnızca alt-dize eşleşmesiyle bulunamayacak etiketler için; eşleşmeyenler
# otomatik olarak veri_turu alt-dize taramasına düşer.
TAG_SYNONYMS: dict[str, str] = {
    "ad-soyad": "Kimlik",
    "ad soyad": "Kimlik",
    "tc kimlik no": "Kimlik",
    "tckn": "Kimlik",
    "kimlik (ad, tc, pasaport)": "Kimlik",
    "seyahat bilgileri": "Kimlik",
    "e-posta": "İletişim",
    "eposta": "İletişim",
    "telefon": "İletişim",
    "adres": "İletişim",
    "iletişim (e-posta, telefon, adres)": "İletişim",
    "ödeme / kredi kartı": "Finans",
    "finansal veriler": "Finans",
    "finansal (iban, kart, gelir)": "Finans",
    "iban": "Finans",
    "ip adresi / çerez": "İşlem Güvenliği",
    "teknik veriler (ip, log)": "İşlem Güvenliği",
    "davranışsal / dijital iz (çerez, ip, cihaz)": "İşlem Güvenliği",
    "sağlık verisi": "Sağlık Bilgileri",
    "sağlık": "Sağlık Bilgileri",
    "çalışan verileri": "Özlük",
    "görsel/işitsel (fotoğraf, ses, video)": "Görsel Ve İşitsel Kayıtlar",
}


@runtime_checkable
class CategoryRepository(Protocol):
    """Kategori adı -> alan sözlüğü (veri_turu, amaclar, hukuki_sebepler, ...).

    Anahtarlar NFC normalize edilmiş kategori adları olmalıdır.
    JSON/SQLite/Postgres implementasyonları bu arayüzü sağlar.
    """

    def all_categories(self) -> dict[str, dict]: ...


class Grounding:
    """Etiket -> kategori çözümleme + envanter kaydı getirme."""

    def __init__(
        self,
        repo: CategoryRepository,
        synonyms: dict[str, str] | None = None,
    ) -> None:
        self._repo = repo
        self._synonyms = synonyms if synonyms is not None else TAG_SYNONYMS

    def resolve_categories(self, tags: list[str]) -> set[str]:
        """Gelen etiketleri gerçek envanter kategorilerine eşler.

        Üç aşamalı (sırayla): (1) sinonim sözlüğü, (2) kategori adıyla doğrudan
        eşleşme, (3) etiketin kategori içindeki veri_turu listesinde alt-dize
        taranması. Döndürülen: eşleşen kategori adlarının kümesi.
        """
        cats = self._repo.all_categories()
        norm_keys = {norm(k): k for k in cats}
        norm_synonyms = {norm(k): v for k, v in self._synonyms.items()}
        matched: set[str] = set()

        for tag in tags:
            if not tag:
                continue
            nt = norm(tag)

            # 1) Sinonim
            if nt in norm_synonyms:
                matched.add(norm_synonyms[nt])
                continue

            # 2) Doğrudan kategori adı eşleşmesi
            if nt in norm_keys:
                matched.add(norm_keys[nt])
                continue

            # 3) veri_turu listesinde alt-dize taraması
            found = False
            for cat_name, data in cats.items():
                for vt in data.get("veri_turu", []):
                    nvt = norm(vt)
                    if nt and (nt in nvt or nvt in nt):
                        matched.add(cat_name)
                        found = True
                        break
                if found:
                    break

        return matched

    def inventory_rules(self, tags: list[str]) -> list[InventoryRecord]:
        """Seçilen etiketlere karşılık gelen envanter grounding kayıtları.

        Saklama süresi/tedbirler envanterde büyük ölçüde boş olduğundan bu
        alanlar çoğunlukla boş gelir; prompt katmanı bunu uydurma-yasağıyla ele alır.
        """
        cats = self._repo.all_categories()
        matched = self.resolve_categories(tags)
        records: list[InventoryRecord] = []

        for cat_name in sorted(matched):
            data = cats.get(cat_name, {})
            records.append(
                InventoryRecord(
                    kategori=cat_name,
                    veri_turleri=list(data.get("veri_turu", [])),
                    amaclar=list(data.get("amaclar", [])),
                    hukuki_sebepler=list(data.get("hukuki_sebepler", [])),
                    kisi_gruplari=list(data.get("kisi_grubu", [])),
                    saklama_sureleri=list(data.get("saklama_sureleri", [])),
                    idari_tedbirler=list(data.get("idari_tedbirler", [])),
                    teknik_tedbirler=list(data.get("teknik_tedbirler", [])),
                )
            )
        return records
