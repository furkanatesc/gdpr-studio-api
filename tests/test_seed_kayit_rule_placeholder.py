"""I1: kayit yolunda bos saklama suresi icin TEK placeholder dizesi kullanilmali.

Once ucfarkli talimat vardi: baslik '[Avukat tarafindan doldurulacak]', format_processes
'[envanterde belirtilmemis - UYDURMA]', seed kurali '[Avukat tarafindan belirlenecek]'.
Kayit yolunda (build_kayit_envanter_prompt + seed'deki kayit is kurali) ONAY_BEKLEYEN_PLACEHOLDER
ile ayni dizeye indirgenmeli ve 'bos birak' ifadesi kalkmali (bos birakma C1'i geri getirir)."""

from __future__ import annotations

from app.seed import RULES
from legal_core.prompt import ONAY_BEKLEYEN_PLACEHOLDER


def test_seed_kayit_kurali_placeholder_ile_ayni_dizeyi_kullanir():
    kayit_kurallari = [metin for tur, metin in RULES if tur == "kayit"]
    saklama_kurali = next(m for m in kayit_kurallari if "UYDURMA" in m)
    assert ONAY_BEKLEYEN_PLACEHOLDER in saklama_kurali
    assert "bos birak" not in saklama_kurali.lower()
    assert "boş bırak" not in saklama_kurali.lower()
