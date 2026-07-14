"""Idempotency — aynı (org, Idempotency-Key) ile ÇİFT üretimi önleyen kısa-TTL kilit.

Neden: ağ timeout'unda istemci `POST /generate`i tekrarlarsa ikinci bir model çağrısı
yapılır → çift doküman, çift kota, çift maliyet (mimari review P1). İstemci opsiyonel
`Idempotency-Key` başlığı gönderirse (org, key) üzerinde kısa süreli bir kilit alınır;
kilit duruyorken gelen ikinci istek 409 döner.

Üretilen belge İÇERİĞİ saklanmaz (veri minimizasyonu — ürünün temel vaadi), bu yüzden
yanıt tekrar OYNATILMAZ; kilit yalnızca çift üretimi ve çift faturalamayı engeller.
Başarısız üretimde kilit bırakılır → istemci aynı anahtarla yeniden deneyebilir.

Redis opsiyoneldir: yoksa/erişilemezse fail-open (rate-limit ile aynı davranış).
"""

from __future__ import annotations

import hashlib
import logging
import uuid

from .redis_client import get_redis

_log = logging.getLogger("app.idempotency")

IDEMPOTENCY_TTL_S = 600  # 10 dk — ağ retry'ı için yeterli, kalıcı durum tutmaz
MAX_KEY_LENGTH = 255


def _redis_key(org_id: uuid.UUID, key: str) -> str:
    # Anahtar hash'lenir: sabit uzunluk + istemci girdisi Redis anahtar uzayına sızmaz.
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return f"idem:generate:{org_id}:{digest}"


def claim(org_id: uuid.UUID, key: str | None) -> bool:
    """Kilidi al. True → devam et. False → aynı anahtar zaten işleniyor/işlendi (409).

    Başlık yoksa veya Redis devre dışıysa True (opsiyonel özellik, fail-open).
    """
    if not key:
        return True
    client = get_redis()
    if client is None:
        return True
    try:
        acquired = client.set(_redis_key(org_id, key), "1", nx=True, ex=IDEMPOTENCY_TTL_S)
    except Exception as e:  # Redis op hatası → engelleme, izin ver
        _log.warning("Idempotency Redis hatası (fail-open): %s", e)
        return True
    return bool(acquired)


def release(org_id: uuid.UUID, key: str | None) -> None:
    """Kilidi bırak — üretim BAŞARISIZ olduğunda; aynı anahtarla yeniden denenebilsin."""
    if not key:
        return
    client = get_redis()
    if client is None:
        return
    try:
        client.delete(_redis_key(org_id, key))
    except Exception as e:
        _log.warning("Idempotency kilidi bırakılamadı (TTL ile düşecek): %s", e)
