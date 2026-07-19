import json
from pathlib import Path

from scripts.extract_measures.extract import _split_measure_cell, strip_measure_prefix


def test_split_measure_cell_never_splits_on_comma():
    """Merkezî sapma koruması: tedbir cümlesi iç virgülde BÖLÜNMEZ (split_cell'e geri dönüş regresyonu)."""
    # Tek tedbir, gramatik virgüller içerir → tek parça kalmalı.
    assert _split_measure_cell("Erişim, bilgi güvenliği, kullanım, saklama ve imha") == [
        "Erişim, bilgi güvenliği, kullanım, saklama ve imha"
    ]
    # Satır sonu / noktalı virgül gerçek öğe ayracıdır → bölünür.
    assert _split_measure_cell("Şifreleme yapılır\nLoglama tutulur") == ["Şifreleme yapılır", "Loglama tutulur"]
    assert _split_measure_cell("A tedbiri; B tedbiri") == ["A tedbiri", "B tedbiri"]
    assert _split_measure_cell("") == []


def test_strip_measure_prefix():
    assert strip_measure_prefix("1.Ağ güvenliği sağlanmaktadır.") == "Ağ güvenliği sağlanmaktadır."
    assert strip_measure_prefix("2-  Erişim yetkileri sınırlandırılmaktadır") == "Erişim yetkileri sınırlandırılmaktadır"
    assert strip_measure_prefix("12) Loglama yapılır") == "Loglama yapılır"
    assert strip_measure_prefix("Şifreleme kullanılır") == "Şifreleme kullanılır"  # önek yoksa dokunma
    assert strip_measure_prefix("Tedbirler") == "Tedbirler"  # başlık kelimesi


def test_measures_json_clean_and_no_junk():
    """Commit'li tedbir listesi: gerçek tedbirler, çöp yok, PII yok."""
    path = Path(__file__).resolve().parent.parent / "data" / "measures.json"
    blob = path.read_text(encoding="utf-8")
    measures = json.loads(blob)["tedbirler"]
    assert isinstance(measures, list) and len(measures) >= 30
    groups = set(measures)
    # İnsan denetiminde düşülen tedbir-olmayan değerler geri sızmamalı.
    assert "Diğer" not in groups
    assert "Web Sunucu" not in groups
    # Kanonik: baştaki numara öneki temizlenmiş olmalı.
    assert all(not m[:1].isdigit() for m in measures)
    # Anonimlik: gerçek kurum adı sızmamalı.
    assert "PROGSA" not in blob
