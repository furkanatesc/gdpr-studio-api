from legal_core.models import ProcessRecord
from legal_core.prompt import build_prompt, format_processes


def _rec(alt="Kimlik teyidi", sak=None, **kw):
    return ProcessRecord(
        departman="İK", is_sureci="İşe Giriş", alt_surec=alt, kisi_grubu="Çalışan",
        kategoriler=["Kimlik"], veri_turleri=["Ad"],
        hukuki_sebepler=["5/2ç Hukuki Yükümlülük"], dayanaklar=["4857 s. Kanun"],
        saklama_sureleri=sak if sak is not None else ["İşten ayrılıştan itibaren 10 yıl"],
        **kw,
    )


def test_format_processes_emits_own_legal_basis_and_retention():
    out = format_processes([_rec()])
    assert "İK / İşe Giriş / Kimlik teyidi" in out
    assert "5/2ç Hukuki Yükümlülük" in out
    assert "İşten ayrılıştan itibaren 10 yıl" in out
    assert "Çalışan" in out


def test_format_processes_does_not_emit_aktarim():
    """format_processes build_prompt (canlı: /api/generate + cerez) tarafından paylaşılıyor;
    Alıcı/Aktarım satırı burada basılırsa global sektör şablonlarındaki (client_id yok)
    gerçek alıcı adları ilgisiz müvekkillerin belgesine sızar (I3 bulgusu). Kayıt yolu
    aktarımı kendi formatter'ında (build_kayit_envanter_prompt) koşulsuz basıyor."""
    out = format_processes([_rec(aktarim=["SGK"])])
    assert "Alıcı/Aktarım" not in out
    assert "SGK" not in out


def test_format_processes_marks_missing_retention_as_do_not_invent():
    out = format_processes([_rec(sak=[])])
    assert "UYDURMA" in out  # boş saklama → uydurma yasağı ibaresi


def test_format_processes_cap_is_not_silent():
    recs = [_rec(alt=f"Alt {i}") for i in range(10)]
    out = format_processes(recs, cap=3)
    assert "Alt 0" in out and "Alt 2" in out
    assert "Alt 3" not in out
    assert "10" in out and "kırpıldı" in out.lower()  # kirpma acikca bildirilir


def test_format_processes_empty_returns_empty_string():
    assert format_processes([]) == ""


def test_build_prompt_includes_processes_when_given():
    p = build_prompt("aydinlatma", {"type": "aydinlatma"}, [], ["kural"], processes=[_rec()])
    assert "SÜREÇ" in p.upper()
    assert "İşten ayrılıştan itibaren 10 yıl" in p


def test_build_prompt_without_processes_is_unchanged():
    """Regresyon: süreç yoksa prompt eski davranışta kalır (kategori yolu)."""
    p = build_prompt("aydinlatma", {"type": "aydinlatma"}, [], ["kural"])
    assert "SÜREÇ" not in p.upper()
    assert "KVKK ENVANTERİ" in p
