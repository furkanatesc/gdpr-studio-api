"""DPA-İncele: kanonik KVKK m.12 kontrol listesi + review veri modelleri — saf.

(Task 3 bu dosyaya prompt-güdümlü JSON analiz fonksiyonlarını ekler.)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ReviewItem:
    id: str
    baslik: str
    kvkk_ref: str
    aranan: str
    kirmizi_bayrak: bool = False


@dataclass(frozen=True)
class ReviewFinding:
    madde_id: str
    durum: str
    alinti: str
    gerekce: str
    oneri: str


@dataclass(frozen=True)
class DpaReviewResult:
    bulgular: list[ReviewFinding]
    uygun: int
    eksik: int
    yetersiz: int
    kirmizi_bayrak: int
    disclaimer: str


@dataclass(frozen=True)
class ReviewContext:
    veri_sorumlusu: str
    isleyen_adi: str | None
    yurt_disi: bool
    aktarim_adlari: list[str]
    kategoriler: list[str]


DPA_CHECKLIST: list[ReviewItem] = [
    ReviewItem("belgeli_talimat", "Belgelenmiş talimatla işleme",
               "KVKK m.12", "İşleyen kişisel veriyi yalnız veri sorumlusunun yazılı/belgelenmiş talimatıyla işler."),
    ReviewItem("konu_kapsam", "İşleme konusu, süresi, amacı ve veri kategorileri",
               "KVKK m.12", "Sözleşme işlemenin konusunu, süresini, amacını ve kapsanan veri kategorilerini tanımlar."),
    ReviewItem("gizlilik", "Gizlilik taahhüdü",
               "KVKK m.12/3", "İşleyen ve çalışanları için süresiz gizlilik/sır saklama yükümlülüğü."),
    ReviewItem("tedbirler", "Teknik ve idari tedbirler",
               "KVKK m.12/1", "İşleyen uygun güvenlik düzeyini sağlayacak teknik ve idari tedbirleri taahhüt eder."),
    ReviewItem("alt_isleyen", "Alt-işleyen onay prosedürü",
               "KVKK m.12", "Alt-işleyen kullanımı veri sorumlusunun önceden yazılı iznine bağlıdır."),
    ReviewItem("ihlal_bildirim", "Veri ihlali bildirim yükümlülüğü ve süresi",
               "KVKK m.12/5", "İhlal en kısa sürede (≤72 saat) veri sorumlusuna bildirilir.", kirmizi_bayrak=True),
    ReviewItem("sozlesme_sonu", "Sözleşme sonunda silme/iade",
               "KVKK m.12", "Sözleşme bitiminde veriler veri sorumlusuna iade veya güvenli imha edilir.", kirmizi_bayrak=True),
    ReviewItem("denetim", "Denetim hakkı",
               "KVKK m.12", "Veri sorumlusuna denetim/uyum doğrulama hakkı tanınır."),
    ReviewItem("yurt_disi", "Yurt dışı aktarım güvenceleri",
               "KVKK m.9", "Yurt dışı aktarım varsa taahhütname/SCC/Kurul kararı referansı bulunur; muğlak ifade yok."),
    ReviewItem("kendi_amaci", "İşleyenin veriyi kendi amacı için kullanmaması",
               "KVKK m.12", "İşleyenin kişisel veriyi kendi ticari amaçları için kullanmasına izin YOKTUR.", kirmizi_bayrak=True),
    ReviewItem("ilgili_kisi", "İlgili kişi haklarına destek",
               "KVKK m.11", "İşleyen, ilgili kişi başvurularının karşılanmasında veri sorumlusuna yardımcı olur."),
]


class ReviewParseError(Exception):
    """Model çıktısı geçerli JSON dizisine çözülemedi."""


_DISCLAIMER = (
    "Bu analiz yapay zekâ taslağıdır; hukuki görüş yerine geçmez. Nihai değerlendirme "
    "avukat incelemesi gerektirir."
)
_VALID_DURUM = {"var", "eksik", "yetersiz"}
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def build_dpa_review_prompt(
    text: str, context: ReviewContext, checklist: list[ReviewItem] = DPA_CHECKLIST
) -> str:
    items = "\n".join(
        f'- id="{it.id}" | {it.baslik} ({it.kvkk_ref}): {it.aranan}'
        + (" [KIRMIZI BAYRAK]" if it.kirmizi_bayrak else "")
        for it in checklist
    )
    yurt = "VAR" if context.yurt_disi else "YOK/bilinmiyor"
    aktarimlar = ", ".join(context.aktarim_adlari) or "—"
    kategoriler = ", ".join(context.kategoriler) or "—"
    isleyen = context.isleyen_adi or "(belirtilmedi)"
    return f"""Sen bir KVKK uyum uzmanısın. Aşağıdaki Veri İşleyen Sözleşmesi (DPA) metnini,
verilen kontrol listesine göre madde madde değerlendir.

MÜVEKKİL BAĞLAMI (envanterden):
- Veri sorumlusu: {context.veri_sorumlusu}
- Değerlendirilen veri işleyen: {isleyen}
- Envanterde yurt dışı aktarım: {yurt}
- Aktarım alıcıları: {aktarimlar}
- Kapsanan veri kategorileri: {kategoriler}

KONTROL LİSTESİ (her madde için ayrı değerlendir):
{items}

DEĞERLENDİRME KURALLARI:
- Her madde için durum: "var" (açıkça karşılanıyor), "eksik" (hiç yok) veya
  "yetersiz" (var ama muğlak/koşulu zayıf).
- "alinti": ilgili sözleşme ifadesinden KISA birebir alıntı (yoksa boş string).
- "gerekce": neden bu durumu verdiğin (1-2 cümle).
- "oneri": eksik/yetersizse eklenecek/düzeltilecek somut madde metni (var ise boş string).
- KIRMIZI BAYRAK maddelerinde bağlamı dikkate al: örn. envanterde yurt dışı aktarım VARSA
  ve sözleşmede m.9 güvencesi yoksa "eksik" ver ve bunu gerekçede belirt.
- UYDURMA: metinde olmayan bir hükmü "var" sayma.

ÇIKTI: YALNIZCA bir JSON dizisi döndür (başka hiçbir metin, açıklama veya kod çiti YOK).
Her eleman: {{"madde_id": "...", "durum": "...", "alinti": "...", "gerekce": "...", "oneri": "..."}}
Kontrol listesindeki HER madde için tam bir eleman olmalı.

SÖZLEŞME METNİ:
\"\"\"
{text}
\"\"\"
"""


def parse_review_json(
    raw: str, checklist: list[ReviewItem] = DPA_CHECKLIST
) -> list[ReviewFinding]:
    cleaned = _FENCE_RE.sub("", raw).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ReviewParseError(str(e)) from e
    if not isinstance(data, list):
        raise ReviewParseError("JSON dizisi bekleniyordu.")
    by_id: dict[str, ReviewFinding] = {}
    for el in data:
        if not isinstance(el, dict):
            continue
        mid = str(el.get("madde_id", "")).strip()
        durum = str(el.get("durum", "")).strip()
        if durum not in _VALID_DURUM:
            durum = "yetersiz"
        by_id[mid] = ReviewFinding(
            madde_id=mid, durum=durum,
            alinti=str(el.get("alinti", "") or ""),
            gerekce=str(el.get("gerekce", "") or ""),
            oneri=str(el.get("oneri", "") or ""),
        )
    out: list[ReviewFinding] = []
    for it in checklist:
        f = by_id.get(it.id)
        if f is None:
            f = ReviewFinding(it.id, "yetersiz", "", "Model bu maddeyi değerlendirmedi.", "")
        out.append(f)
    return out


def review_dpa(
    text: str,
    context: ReviewContext,
    *,
    provider,
    max_tokens: int = 8000,
    checklist: list[ReviewItem] = DPA_CHECKLIST,
) -> DpaReviewResult:
    prompt = build_dpa_review_prompt(text, context, checklist)
    result = provider.generate(prompt, max_tokens=max_tokens)
    try:
        findings = parse_review_json(result.text, checklist)
    except ReviewParseError:
        retry = provider.generate(
            prompt + "\n\nHATIRLATMA: Çıktı YALNIZCA geçerli JSON dizisi olmalı.",
            max_tokens=max_tokens,
        )
        findings = parse_review_json(retry.text, checklist)
    flag_ids = {it.id for it in checklist if it.kirmizi_bayrak}
    uygun = sum(1 for f in findings if f.durum == "var")
    eksik = sum(1 for f in findings if f.durum == "eksik")
    yetersiz = sum(1 for f in findings if f.durum == "yetersiz")
    kirmizi = sum(1 for f in findings if f.madde_id in flag_ids and f.durum != "var")
    return DpaReviewResult(
        bulgular=findings, uygun=uygun, eksik=eksik, yetersiz=yetersiz,
        kirmizi_bayrak=kirmizi, disclaimer=_DISCLAIMER,
    )
