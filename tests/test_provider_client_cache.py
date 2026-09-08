"""_AsyncClientCache birim testleri — bounded LRU + evict'te aclose.

Gerçek AsyncAnthropic yaratılmaz: factory enjekte edilir, sahte client'lar
async aclose() sunar. Amaç: aynı anahtar→aynı client (havuz reuse), farklı
anahtar→farklı client, maxsize aşınca LRU-en-eski evict + aclose, touch LRU
sırasını günceller, aclose_all hepsini kapatır.
"""

import asyncio

from legal_core.provider import _AsyncClientCache


class _FakeClient:
    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


def _factory():
    """Her çağrıda yeni sahte client + kaç kez çağrıldığını sayan closure."""
    calls = {"n": 0}
    created: list[_FakeClient] = []

    def make():
        calls["n"] += 1
        c = _FakeClient(f"c{calls['n']}")
        created.append(c)
        return c

    return make, calls, created


def test_ayni_anahtar_ayni_client_factory_bir_kez():
    make, calls, _ = _factory()
    cache = _AsyncClientCache(maxsize=4)

    async def go():
        a = await cache.get(("k", 60.0, 2), make)
        b = await cache.get(("k", 60.0, 2), make)
        return a, b

    a, b = asyncio.run(go())
    assert a is b
    assert calls["n"] == 1


def test_farkli_anahtar_farkli_client():
    make, calls, _ = _factory()
    cache = _AsyncClientCache(maxsize=4)

    async def go():
        a = await cache.get(("k1", 60.0, 2), make)
        b = await cache.get(("k2", 60.0, 2), make)
        return a, b

    a, b = asyncio.run(go())
    assert a is not b
    assert calls["n"] == 2


def test_maxsize_asinca_en_eski_evict_ve_aclose():
    make, _, created = _factory()
    cache = _AsyncClientCache(maxsize=2)

    async def go():
        await cache.get(("k1", 60.0, 2), make)  # created[0]
        await cache.get(("k2", 60.0, 2), make)  # created[1]
        await cache.get(("k3", 60.0, 2), make)  # created[2] → k1 evict

    asyncio.run(go())
    assert created[0].closed is True  # en eski (k1) kapatıldı
    assert created[1].closed is False
    assert created[2].closed is False


def test_touch_lru_sirasini_gunceller():
    make, _, created = _factory()
    cache = _AsyncClientCache(maxsize=2)

    async def go():
        await cache.get(("k1", 60.0, 2), make)  # created[0]
        await cache.get(("k2", 60.0, 2), make)  # created[1]
        await cache.get(("k1", 60.0, 2), make)  # k1 touch → en yeni
        await cache.get(("k3", 60.0, 2), make)  # created[2] → k2 evict (k1 değil)

    asyncio.run(go())
    assert created[1].closed is True  # k2 evict edildi
    assert created[0].closed is False  # k1 dokunulduğu için kaldı


def test_aclose_all_hepsini_kapatir_ve_bosaltir():
    make, _, created = _factory()
    cache = _AsyncClientCache(maxsize=4)

    async def go():
        await cache.get(("k1", 60.0, 2), make)
        await cache.get(("k2", 60.0, 2), make)
        await cache.aclose_all()

    asyncio.run(go())
    assert all(c.closed for c in created)
    # kapanıştan sonra yeni get yeni client yaratır (cache boşaldı)
    make2, calls2, _ = _factory()

    async def go2():
        await cache.get(("k1", 60.0, 2), make2)

    asyncio.run(go2())
    assert calls2["n"] == 1
