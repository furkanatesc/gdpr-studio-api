from scripts.extract_measures.extract import strip_measure_prefix


def test_strip_measure_prefix():
    assert strip_measure_prefix("1.Ağ güvenliği sağlanmaktadır.") == "Ağ güvenliği sağlanmaktadır."
    assert strip_measure_prefix("2-  Erişim yetkileri sınırlandırılmaktadır") == "Erişim yetkileri sınırlandırılmaktadır"
    assert strip_measure_prefix("12) Loglama yapılır") == "Loglama yapılır"
    assert strip_measure_prefix("Şifreleme kullanılır") == "Şifreleme kullanılır"  # önek yoksa dokunma
    assert strip_measure_prefix("Tedbirler") == "Tedbirler"  # başlık kelimesi
