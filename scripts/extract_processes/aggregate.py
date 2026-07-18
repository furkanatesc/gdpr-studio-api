"""Envanter satırlarını (departman, iş süreci, alt süreç, kişi grubu) bazında süreçlere toplar."""

from __future__ import annotations

from scripts.enrich_categories.aggregate import clean_tokens

# data JSONB'de tutulan çok-değerli alanlar (boş→boş).
DATA_LIST_FIELDS = (
    "kategoriler", "veri_turleri", "islem", "amaclar", "hukuki_sebepler", "dayanaklar",
    "saklama_sureleri", "ortam_format", "konum", "idari_tedbirler", "teknik_tedbirler",
    "alici_grubu", "alici",
)
# data JSONB'de tutulan tekil alanlar (ilk dolu değer kazanır).
DATA_SINGLE_FIELDS = (
    "departman_kodu", "rol", "veri_kayit_sistemi", "kaynak", "yurtdisi_aktarim",
    "alici_niteligi", "aktarim_metodu", "ulke", "aciklama",
)


def aggregate_processes(rows: list[dict], sector: str) -> list[dict]:
    """Satırları süreçlere topla. Anahtar: (departman, is_sureci, alt_surec, kisi_grubu)."""
    acc: dict[tuple, dict] = {}
    for row in rows:
        key = (
            row.get("departman", ""), row.get("is_sureci", ""),
            row.get("alt_surec", ""), row.get("kisi_grubu", ""),
        )
        if not key[3]:  # kişi grubu zorunlu (sorgu ekseni)
            continue
        bucket = acc.setdefault(key, {f: [] for f in DATA_LIST_FIELDS})
        for f in DATA_LIST_FIELDS:
            bucket[f].extend(row.get(f, []) or [])
        for f in DATA_SINGLE_FIELDS:
            if not bucket.get(f) and row.get(f):
                bucket[f] = row[f]

    out: list[dict] = []
    for (dep, isr, alt, kg) in sorted(acc, key=lambda k: (k[0], k[1], k[2], k[3])):
        raw = acc[(dep, isr, alt, kg)]
        data = {f: clean_tokens(raw[f]) for f in DATA_LIST_FIELDS}
        for f in DATA_SINGLE_FIELDS:
            data[f] = raw.get(f, "") if isinstance(raw.get(f), str) else ""
        out.append({
            "sector": sector, "kisi_grubu": kg,
            "departman": dep, "is_sureci": isr, "alt_surec": alt,
            "data": data,
        })
    return out
