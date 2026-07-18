"""Süreç ekseni grounding — kategori yoluna dokunmadan (fallback korunur)."""

from legal_core.adapters import DictCategoryRepository, DictProcessRepository
from legal_core.grounding import Grounding

_PROCS = [
    {
        "sector": "sirket", "kisi_grubu": "Çalışan", "departman": "İK",
        "is_sureci": "İşe Giriş", "alt_surec": "Kimlik teyidi",
        "data": {
            "kategoriler": ["Kimlik"], "veri_turleri": ["Ad", "Soyad"],
            "hukuki_sebepler": ["5/2ç Hukuki Yükümlülük"], "dayanaklar": ["4857 s. Kanun"],
            "saklama_sureleri": ["İşten ayrılıştan itibaren 10 yıl"], "amaclar": [],
            "islem": ["Elde Etme"], "ortam_format": [], "konum": [],
            "idari_tedbirler": [], "teknik_tedbirler": [],
        },
    },
    {
        "sector": "sirket", "kisi_grubu": "Çalışan Adayı", "departman": "İK",
        "is_sureci": "İşe Alım", "alt_surec": "Başvuru",
        "data": {
            "kategoriler": ["Kimlik"], "veri_turleri": ["CV"],
            "hukuki_sebepler": ["5/2f Meşru Menfaat"], "dayanaklar": [],
            "saklama_sureleri": ["1 yıl"], "amaclar": [], "islem": [],
            "ortam_format": [], "konum": [], "idari_tedbirler": [], "teknik_tedbirler": [],
        },
    },
    {
        "sector": "otel", "kisi_grubu": "Çalışan", "departman": "TEKNİK",
        "is_sureci": "Cihaz Takip", "alt_surec": "Kalibrasyon",
        "data": {
            "kategoriler": ["Kimlik"], "veri_turleri": ["Ad"], "hukuki_sebepler": [],
            "dayanaklar": [], "saklama_sureleri": [], "amaclar": [], "islem": [],
            "ortam_format": [], "konum": [], "idari_tedbirler": [], "teknik_tedbirler": [],
        },
    },
]


def _grounding():
    return Grounding(DictCategoryRepository({}), process_repo=DictProcessRepository(_PROCS))


def test_process_rules_filters_by_sector_and_group():
    recs = _grounding().process_rules("sirket", "Çalışan")
    assert len(recs) == 1
    r = recs[0]
    assert r.is_sureci == "İşe Giriş"
    assert r.hukuki_sebepler == ["5/2ç Hukuki Yükümlülük"]
    assert r.saklama_sureleri == ["İşten ayrılıştan itibaren 10 yıl"]


def test_process_rules_sector_isolation():
    """Sektör A'nın süreci B'ye sızmaz."""
    recs = _grounding().process_rules("otel", "Çalışan")
    assert [r.departman for r in recs] == ["TEKNİK"]


def test_process_rules_all_groups_when_none():
    """kisi_grubu=None → sektörün tümü (kayit/ROPA yolu)."""
    recs = _grounding().process_rules("sirket", None)
    assert len(recs) == 2


def test_process_rules_empty_without_sector_or_repo():
    assert _grounding().process_rules(None, "Çalışan") == []
    assert Grounding(DictCategoryRepository({})).process_rules("sirket", "Çalışan") == []


def test_process_rules_unknown_group_returns_empty():
    assert _grounding().process_rules("sirket", "Ziyaretçi") == []
