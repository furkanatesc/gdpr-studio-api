"""PostgresSemanticMatcher — eşik mantığı + fail-soft (Postgres'siz, fake ile)."""

from app.semantic import PostgresSemanticMatcher


class _FakeEmbedder:
    def embed_query(self, text):
        return [1.0, 0.0]


class _Matcher(PostgresSemanticMatcher):
    """_nearest'ı sahteyle değiştirir — SQL/Postgres gerekmez."""

    def __init__(self, threshold, nearest):
        # session kullanılmaz (testte); embedder fake.
        super().__init__(session=None, embedder=_FakeEmbedder(), threshold=threshold)
        self._fake_nearest = nearest

    def _nearest(self, qvec):
        return self._fake_nearest


def test_esik_ustu_eslesir():
    m = _Matcher(threshold=0.80, nearest=("İletişim", 0.91))
    assert m.best_category("konum verisi") == ("İletişim", 0.91)


def test_esik_alti_none_doner():
    m = _Matcher(threshold=0.80, nearest=("İletişim", 0.55))
    assert m.best_category("konum verisi") is None


def test_komsu_yoksa_none():
    m = _Matcher(threshold=0.80, nearest=None)
    assert m.best_category("konum verisi") is None


def test_fail_soft_istisna_none():
    def _boom(qvec):
        raise RuntimeError("db down")

    m = _Matcher(threshold=0.80, nearest=None)
    m._nearest = _boom  # type: ignore[assignment]
    # Üretim akışı semantik hata yüzünden PATLAMAMALI → None.
    assert m.best_category("konum verisi") is None
