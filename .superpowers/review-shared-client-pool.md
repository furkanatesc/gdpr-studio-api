# Review — shared AsyncAnthropic client pooling

Range: main(81eccf3)..124b592

## git log
124b592 perf(uretim): AnthropicProvider async client'ı havuzla (shared LRU) — gerçek connection reuse

## diff --stat
 legal_core/provider.py              | 110 ++++++++++++++++++++++++++---------
 tests/conftest.py                   |   9 +++
 tests/test_provider_agenerate.py    |  18 +++---
 tests/test_provider_astream.py      |  13 ++---
 tests/test_provider_client_cache.py | 113 ++++++++++++++++++++++++++++++++++++
 tests/test_provider_stop_reason.py  |  12 ----
 tests/test_provider_timeout.py      |  13 +++--
 7 files changed, 228 insertions(+), 60 deletions(-)

## diff -U12
```diff
diff --git a/legal_core/provider.py b/legal_core/provider.py
index d8ed328..ab4f3f6 100644
--- a/legal_core/provider.py
+++ b/legal_core/provider.py
@@ -1,24 +1,25 @@
 """Model sağlayıcı soyutlaması — Claude birincil, sağlayıcı değiştirilebilir.
 
 legal_core saf kalır: anthropic SDK yalnızca AnthropicProvider içinde lazy import
 edilir. BYOK (kullanıcının kendi anahtarı) ve managed (sunucu anahtarı) yolları
 aynı arayüzü kullanır — fark yalnızca hangi api_key'in geçtiğidir.
 """
 
 from __future__ import annotations
 
-from collections.abc import AsyncIterator
+from collections import OrderedDict
+from collections.abc import AsyncIterator, Callable
 from dataclasses import dataclass
-from typing import Protocol, runtime_checkable
+from typing import Any, Protocol, runtime_checkable
 
 DEFAULT_MODEL = "claude-sonnet-4-6"
 DEFAULT_MAX_TOKENS = 8000
 # Dayanıklılık varsayılanları: timeout/retry OLMADAN upstream asılırsa event loop +
 # DB bağlantısı süresiz tutulur → istek yanıtsız kalır. Sınırlı timeout + az sayıda
 # retry bunu keser.
 DEFAULT_TIMEOUT_S = 60.0
 DEFAULT_MAX_RETRIES = 2
 
 
 @dataclass(frozen=True)
 class ProviderResult:
@@ -29,24 +30,66 @@ class ProviderResult:
     # Anthropic'in "stop_reason"u: "max_tokens" ise metin cumle ortasinda kesilmis
     # olabilir. None -> eski cagrilar (varsayilan) kirilmasin.
     stop_reason: str | None = None
 
 
 @runtime_checkable
 class AsyncModelProvider(Protocol):
     async def agenerate(self, prompt: str, *, max_tokens: int = DEFAULT_MAX_TOKENS) -> ProviderResult: ...
 
     def astream(self, prompt: str, *, max_tokens: int = DEFAULT_MAX_TOKENS): ...
 
 
+class _AsyncClientCache:
+    """Anahtar başına paylaşılan async model istemcilerinin sınırlı LRU önbelleği.
+
+    Havuz reuse: aynı (api_key, timeout_s, max_retries) → aynı AsyncAnthropic (dolayısıyla
+    aynı httpx bağlantı havuzu/keepalive). Her çağrıda yeni client + taze TLS handshake
+    yerine yeniden kullanım. BYOK anahtarları sınırsız büyümesin diye maxsize; kapasite
+    aşılınca EN ESKİ (LRU) client evict edilip aclose ile kapatılır. Süreç tek event
+    loop'ta (uvicorn worker) çalıştığından ek kilit gerekmez.
+    """
+
+    def __init__(self, maxsize: int = 32) -> None:
+        self._cache: OrderedDict[tuple[Any, ...], Any] = OrderedDict()
+        self._maxsize = maxsize
+
+    async def get(self, key: tuple[Any, ...], factory: Callable[[], Any]) -> Any:
+        client = self._cache.get(key)
+        if client is not None:
+            self._cache.move_to_end(key)  # LRU: dokunulan en yeni
+            return client
+        client = factory()
+        self._cache[key] = client
+        if len(self._cache) > self._maxsize:
+            _, evicted = self._cache.popitem(last=False)  # en eski
+            await evicted.aclose()
+        return client
+
+    async def aclose_all(self) -> None:
+        clients = list(self._cache.values())
+        self._cache.clear()
+        for c in clients:
+            await c.aclose()
+
+
+# Modül-seviye havuz: aynı süreçteki tüm istekler paylaşır.
+_CLIENT_CACHE = _AsyncClientCache()
+
+
+async def aclose_all_clients() -> None:
+    """Uygulama kapanışında (lifespan/shutdown) havuzdaki tüm async client'ları kapatır."""
+    await _CLIENT_CACHE.aclose_all()
+
+
 class AnthropicProvider:
     """Anthropic Claude implementasyonu (BYOK veya managed anahtar)."""
 
     def __init__(
         self,
         api_key: str,
         model: str = DEFAULT_MODEL,
         *,
         timeout_s: float = DEFAULT_TIMEOUT_S,
         max_retries: int = DEFAULT_MAX_RETRIES,
     ) -> None:
         if not api_key:
@@ -54,62 +97,73 @@ class AnthropicProvider:
         self._api_key = api_key
         self._model = model
         self._timeout_s = timeout_s
         self._max_retries = max_retries
         # astream() bittikten sonra final usage burada saklanır.
         self.last_result: ProviderResult | None = None
 
     @property
     def model(self) -> str:
         return self._model
 
     async def agenerate(self, prompt: str, *, max_tokens: int = DEFAULT_MAX_TOKENS) -> ProviderResult:
-        """AsyncAnthropic ile tek-seferlik (stream'siz) üretim; await messages.create."""
-        async with self._aclient() as client:
-            message = await client.messages.create(
-                model=self._model,
-                max_tokens=max_tokens,
-                messages=[{"role": "user", "content": prompt}],
-            )
+        """AsyncAnthropic ile tek-seferlik (stream'siz) üretim; await messages.create.
+
+        Client havuzdan gelir (paylaşılan) — per-call KAPATILMAZ; havuz yaşamı boyunca
+        yeniden kullanılır (kapanış aclose_all_clients ile)."""
+        client = await self._aclient()
+        message = await client.messages.create(
+            model=self._model,
+            max_tokens=max_tokens,
+            messages=[{"role": "user", "content": prompt}],
+        )
         text = message.content[0].text
         usage = getattr(message, "usage", None)
         result = ProviderResult(
             text=text,
             model=self._model,
             input_tokens=getattr(usage, "input_tokens", 0) or 0,
             output_tokens=getattr(usage, "output_tokens", 0) or 0,
             stop_reason=getattr(message, "stop_reason", None),
         )
         self.last_result = result
         return result
 
-    def _aclient(self):
-        """Async Anthropic istemcisi (lazy import: legal_core saf kalır)."""
+    async def _aclient(self):
+        """Havuzlanmış async Anthropic istemcisi — (api_key,timeout,retries) başına paylaşılır."""
+        key = (self._api_key, self._timeout_s, self._max_retries)
+        return await _CLIENT_CACHE.get(key, self._build_client)
+
+    def _build_client(self):
+        """Yeni AsyncAnthropic (lazy import: legal_core saf kalır). Yalnız cache-miss'te çağrılır."""
         import httpx
         from anthropic import AsyncAnthropic
 
         return AsyncAnthropic(
             api_key=self._api_key,
             timeout=httpx.Timeout(self._timeout_s),
             max_retries=self._max_retries,
         )
 
     async def astream(self, prompt: str, *, max_tokens: int = DEFAULT_MAX_TOKENS) -> AsyncIterator[str]:
-        """Metin delta'larını akıtır; bitince final usage'ı self.last_result'a yazar."""
+        """Metin delta'larını akıtır; bitince final usage'ı self.last_result'a yazar.
+
+        Client havuzdan gelir (paylaşılan) — per-call KAPATILMAZ; yalnız RESPONSE
+        (messages.stream) kapatılır."""
         self.last_result = None
-        async with self._aclient() as client:
-            async with client.messages.stream(
+        client = await self._aclient()
+        async with client.messages.stream(
+            model=self._model,
+            max_tokens=max_tokens,
+            messages=[{"role": "user", "content": prompt}],
+        ) as s:
+            async for delta in s.text_stream:
+                yield delta
+            final = await s.get_final_message()
+            usage = getattr(final, "usage", None)
+            self.last_result = ProviderResult(
+                text="",
                 model=self._model,
-                max_tokens=max_tokens,
-                messages=[{"role": "user", "content": prompt}],
-            ) as s:
-                async for delta in s.text_stream:
-                    yield delta
-                final = await s.get_final_message()
-                usage = getattr(final, "usage", None)
-                self.last_result = ProviderResult(
-                    text="",
-                    model=self._model,
-                    input_tokens=getattr(usage, "input_tokens", 0) or 0,
-                    output_tokens=getattr(usage, "output_tokens", 0) or 0,
-                    stop_reason=getattr(final, "stop_reason", None),
-                )
+                input_tokens=getattr(usage, "input_tokens", 0) or 0,
+                output_tokens=getattr(usage, "output_tokens", 0) or 0,
+                stop_reason=getattr(final, "stop_reason", None),
+            )
diff --git a/tests/conftest.py b/tests/conftest.py
index 57492b6..a12cd65 100644
--- a/tests/conftest.py
+++ b/tests/conftest.py
@@ -15,24 +15,25 @@ import pytest
 from fastapi.testclient import TestClient
 from sqlalchemy import create_engine
 from sqlalchemy.orm import sessionmaker
 from sqlalchemy.pool import StaticPool
 
 import app.config as config_module
 from app.auth.identity import Identity, get_current_identity
 from app.db import Base, get_session
 from app.email.sender import reset_email_sender
 from app.main import app
 from app.models import BusinessRule, Category
 from app.redis_client import reset_redis
+from legal_core.provider import _CLIENT_CACHE
 
 _DEV_IDENTITY = Identity(
     user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
     org_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
     role="yonetici",
     email="dev@kvkkyonetim.local",
 )
 
 # /api/categories ve grounding için temsili minimum seed (gerçek kategori adları).
 _SEED_CATEGORIES = [
     Category(name="Kimlik", data={"veri_turu": ["ad", "soyad"], "hukuki_sebepler": ["5/2-ç"]}),
     Category(name="İletişim", data={"veri_turu": ["e-posta"], "hukuki_sebepler": ["5/2-f"]}),
@@ -185,12 +186,20 @@ def client_fresh(db_session):
     with _dev_bypass_client(db_session) as c:
         yield c
 
 
 @pytest.fixture()
 def client_no_account(db_session):
     """dev-bypass aktif, DB temiz, bootstrap ÇAĞRILMADI → /me 403 döndürür.
 
     client_fresh ile özdeş kurulum; fixture adı "kullanıcı yok → 403" testinin amacını açıklar.
     """
     with _dev_bypass_client(db_session) as c:
         yield c
+
+
+@pytest.fixture(autouse=True)
+def clear_provider_cache():
+    """Provider cache'ini her test öncesinde temizle — test izolasyonu."""
+    _CLIENT_CACHE._cache.clear()
+    yield
+    _CLIENT_CACHE._cache.clear()
diff --git a/tests/test_provider_agenerate.py b/tests/test_provider_agenerate.py
index 16f58d7..038ce5e 100644
--- a/tests/test_provider_agenerate.py
+++ b/tests/test_provider_agenerate.py
@@ -17,51 +17,53 @@ class _FakeAsyncMessages:
         msg.content = [SimpleNamespace(text="agenerate test metin")]
         msg.usage = SimpleNamespace(input_tokens=5, output_tokens=10)
         msg.stop_reason = self._stop_reason
         return msg
 
 
 class _FakeAsyncClient:
     """Faked AsyncAnthropic istemcisi."""
 
     def __init__(self, stop_reason="end_turn"):
         self.messages = _FakeAsyncMessages(stop_reason)
 
-    async def __aenter__(self):
-        return self
-
-    async def __aexit__(self, *a):
-        return False
-
 
 def test_agenerate_normal_bitiste_result_text_ve_usage_tasir(monkeypatch):
     """agenerate() message.content[0].text, usage, stop_reason'ı ProviderResult'a taşır."""
     p = AnthropicProvider("sk-fake", model="claude-x")
     fake_client = _FakeAsyncClient("end_turn")
-    monkeypatch.setattr(p, "_aclient", lambda: fake_client)
+
+    async def _fake_aclient():
+        return fake_client
+
+    monkeypatch.setattr(p, "_aclient", _fake_aclient)
 
     async def _run():
         return await p.agenerate("PROMPT", max_tokens=100)
 
     result = asyncio.run(_run())
 
     assert result.text == "agenerate test metin"
     assert result.input_tokens == 5
     assert result.output_tokens == 10
     assert result.stop_reason == "end_turn"
     assert result.model == "claude-x"
     assert p.last_result == result
 
 
 def test_agenerate_max_tokensta_stop_reason_tasir(monkeypatch):
     """agenerate() max_tokens kesintisinde stop_reason "max_tokens" olur."""
     p = AnthropicProvider("sk-fake", model="claude-y")
     fake_client = _FakeAsyncClient("max_tokens")
-    monkeypatch.setattr(p, "_aclient", lambda: fake_client)
+
+    async def _fake_aclient():
+        return fake_client
+
+    monkeypatch.setattr(p, "_aclient", _fake_aclient)
 
     async def _run():
         return await p.agenerate("PROMPT")
 
     result = asyncio.run(_run())
 
     assert result.stop_reason == "max_tokens"
     assert p.last_result.stop_reason == "max_tokens"
diff --git a/tests/test_provider_astream.py b/tests/test_provider_astream.py
index d02ec2d..0829d67 100644
--- a/tests/test_provider_astream.py
+++ b/tests/test_provider_astream.py
@@ -28,34 +28,33 @@ class _FakeStreamCM:
 
     async def __aexit__(self, *a):
         return False
 
     async def get_final_message(self):
         return self._final
 
 
 class _FakeAsyncClient:
     def __init__(self, cm):
         self.messages = SimpleNamespace(stream=lambda **kw: cm)
 
-    async def __aenter__(self):
-        return self
-
-    async def __aexit__(self, *a):
-        return False
-
 
 def test_astream_deltalari_akitir_ve_last_result_doldurur(monkeypatch):
     p = AnthropicProvider("sk-fake", model="claude-x")
     cm = _FakeStreamCM(["Ay", "dinlatma"], usage=(11, 22), stop_reason="end_turn")
-    monkeypatch.setattr(p, "_aclient", lambda: _FakeAsyncClient(cm))
+    fake_client = _FakeAsyncClient(cm)
+
+    async def _fake_aclient():
+        return fake_client
+
+    monkeypatch.setattr(p, "_aclient", _fake_aclient)
 
     async def _run():
         return [d async for d in p.astream("PROMPT", max_tokens=100)]
 
     deltas = asyncio.run(_run())
 
     assert deltas == ["Ay", "dinlatma"]
     assert p.last_result.input_tokens == 11
     assert p.last_result.output_tokens == 22
     assert p.last_result.stop_reason == "end_turn"
     assert p.last_result.model == "claude-x"
diff --git a/tests/test_provider_client_cache.py b/tests/test_provider_client_cache.py
new file mode 100644
index 0000000..affbe7a
--- /dev/null
+++ b/tests/test_provider_client_cache.py
@@ -0,0 +1,113 @@
+"""_AsyncClientCache birim testleri — bounded LRU + evict'te aclose.
+
+Gerçek AsyncAnthropic yaratılmaz: factory enjekte edilir, sahte client'lar
+async aclose() sunar. Amaç: aynı anahtar→aynı client (havuz reuse), farklı
+anahtar→farklı client, maxsize aşınca LRU-en-eski evict + aclose, touch LRU
+sırasını günceller, aclose_all hepsini kapatır.
+"""
+
+import asyncio
+
+from legal_core.provider import _AsyncClientCache
+
+
+class _FakeClient:
+    def __init__(self, tag: str) -> None:
+        self.tag = tag
+        self.closed = False
+
+    async def aclose(self) -> None:
+        self.closed = True
+
+
+def _factory():
+    """Her çağrıda yeni sahte client + kaç kez çağrıldığını sayan closure."""
+    calls = {"n": 0}
+    created: list[_FakeClient] = []
+
+    def make():
+        calls["n"] += 1
+        c = _FakeClient(f"c{calls['n']}")
+        created.append(c)
+        return c
+
+    return make, calls, created
+
+
+def test_ayni_anahtar_ayni_client_factory_bir_kez():
+    make, calls, _ = _factory()
+    cache = _AsyncClientCache(maxsize=4)
+
+    async def go():
+        a = await cache.get(("k", 60.0, 2), make)
+        b = await cache.get(("k", 60.0, 2), make)
+        return a, b
+
+    a, b = asyncio.run(go())
+    assert a is b
+    assert calls["n"] == 1
+
+
+def test_farkli_anahtar_farkli_client():
+    make, calls, _ = _factory()
+    cache = _AsyncClientCache(maxsize=4)
+
+    async def go():
+        a = await cache.get(("k1", 60.0, 2), make)
+        b = await cache.get(("k2", 60.0, 2), make)
+        return a, b
+
+    a, b = asyncio.run(go())
+    assert a is not b
+    assert calls["n"] == 2
+
+
+def test_maxsize_asinca_en_eski_evict_ve_aclose():
+    make, _, created = _factory()
+    cache = _AsyncClientCache(maxsize=2)
+
+    async def go():
+        await cache.get(("k1", 60.0, 2), make)  # created[0]
+        await cache.get(("k2", 60.0, 2), make)  # created[1]
+        await cache.get(("k3", 60.0, 2), make)  # created[2] → k1 evict
+
+    asyncio.run(go())
+    assert created[0].closed is True  # en eski (k1) kapatıldı
+    assert created[1].closed is False
+    assert created[2].closed is False
+
+
+def test_touch_lru_sirasini_gunceller():
+    make, _, created = _factory()
+    cache = _AsyncClientCache(maxsize=2)
+
+    async def go():
+        await cache.get(("k1", 60.0, 2), make)  # created[0]
+        await cache.get(("k2", 60.0, 2), make)  # created[1]
+        await cache.get(("k1", 60.0, 2), make)  # k1 touch → en yeni
+        await cache.get(("k3", 60.0, 2), make)  # created[2] → k2 evict (k1 değil)
+
+    asyncio.run(go())
+    assert created[1].closed is True  # k2 evict edildi
+    assert created[0].closed is False  # k1 dokunulduğu için kaldı
+
+
+def test_aclose_all_hepsini_kapatir_ve_bosaltir():
+    make, _, created = _factory()
+    cache = _AsyncClientCache(maxsize=4)
+
+    async def go():
+        await cache.get(("k1", 60.0, 2), make)
+        await cache.get(("k2", 60.0, 2), make)
+        await cache.aclose_all()
+
+    asyncio.run(go())
+    assert all(c.closed for c in created)
+    # kapanıştan sonra yeni get yeni client yaratır (cache boşaldı)
+    make2, calls2, _ = _factory()
+
+    async def go2():
+        await cache.get(("k1", 60.0, 2), make2)
+
+    asyncio.run(go2())
+    assert calls2["n"] == 1
diff --git a/tests/test_provider_stop_reason.py b/tests/test_provider_stop_reason.py
index 8579486..8834d00 100644
--- a/tests/test_provider_stop_reason.py
+++ b/tests/test_provider_stop_reason.py
@@ -27,30 +27,24 @@ class _FakeAsyncMessages:
     async def create(self, **kwargs):
         msg = types.SimpleNamespace()
         msg.content = [types.SimpleNamespace(text="metin")]
         msg.usage = types.SimpleNamespace(input_tokens=1, output_tokens=2)
         msg.stop_reason = self._stop_reason
         return msg
 
 
 class _FakeAsyncClient:
     def __init__(self, stop_reason="end_turn", **kwargs):
         self.messages = _FakeAsyncMessages(stop_reason)
 
-    async def __aenter__(self):
-        return self
-
-    async def __aexit__(self, *a):
-        return False
-
 
 def _install_fake_anthropic(monkeypatch, stop_reason):
     fake_mod = types.ModuleType("anthropic")
     fake_mod.AsyncAnthropic = lambda **kw: _FakeAsyncClient(stop_reason=stop_reason)
     monkeypatch.setitem(sys.modules, "anthropic", fake_mod)
 
 
 def test_generate_max_tokensta_stop_reason_tasir(monkeypatch):
     _install_fake_anthropic(monkeypatch, "max_tokens")
     provider = AnthropicProvider("sk-x")
 
     result = asyncio.run(provider.agenerate("prompt"))
@@ -93,30 +87,24 @@ class _FakeStreamCtx:
 class _FakeAsyncMessagesStream:
     def __init__(self, stop_reason):
         self._stop_reason = stop_reason
 
     def stream(self, **kwargs):
         return _FakeStreamCtx(self._stop_reason)
 
 
 class _FakeAsyncClientStream:
     def __init__(self, stop_reason, **kwargs):
         self.messages = _FakeAsyncMessagesStream(stop_reason)
 
-    async def __aenter__(self):
-        return self
-
-    async def __aexit__(self, *a):
-        return False
-
 
 def _install_fake_anthropic_stream(monkeypatch, stop_reason):
     fake_mod = types.ModuleType("anthropic")
     fake_mod.AsyncAnthropic = lambda **kw: _FakeAsyncClientStream(stop_reason)
     monkeypatch.setitem(sys.modules, "anthropic", fake_mod)
 
 
 def test_stream_max_tokensta_last_result_stop_reason_tasir(monkeypatch):
     _install_fake_anthropic_stream(monkeypatch, "max_tokens")
     provider = AnthropicProvider("sk-x")
 
     async def _run():
diff --git a/tests/test_provider_timeout.py b/tests/test_provider_timeout.py
index 37ed2ba..41e6321 100644
--- a/tests/test_provider_timeout.py
+++ b/tests/test_provider_timeout.py
@@ -1,29 +1,28 @@
 """AnthropicProvider dayanıklılığı — H1-4 (mimari review P1/güvenilirlik).
 
 Sorun: Anthropic çağrısında timeout/retry YOKKEN upstream asılırsa event loop + DB
 bağlantısı ~10 dk tutulur → birkaç asılı çağrı isteği yanıtsız bırakır. Fix: client
 `timeout` + `max_retries` ile kurulmalı. Bu test, lazy import edilen
 `anthropic.AsyncAnthropic`'in bu kwarg'larla çağrıldığını yakalar (ağ yok — client sahte).
 """
 
 from __future__ import annotations
 
-import asyncio
 import sys
 import types
 
 import httpx
 
-from legal_core.provider import AnthropicProvider, ProviderResult
+from legal_core.provider import AnthropicProvider
 
 
 class _FakeAsyncMessages:
     def __init__(self, captured):
         self._captured = captured
 
     async def create(self, **kwargs):
         msg = types.SimpleNamespace()
         msg.content = [types.SimpleNamespace(text="metin")]
         msg.usage = types.SimpleNamespace(input_tokens=1, output_tokens=2)
         return msg
 
@@ -43,31 +42,35 @@ class _FakeAsyncClient:
 
 def _install_fake_anthropic(monkeypatch):
     """anthropic modülünü sahtele — `from anthropic import AsyncAnthropic` bunu bulur."""
     fake_mod = types.ModuleType("anthropic")
     fake_mod.AsyncAnthropic = _FakeAsyncClient
     monkeypatch.setitem(sys.modules, "anthropic", fake_mod)
 
 
 def test_generate_client_built_with_timeout_and_retries(monkeypatch):
     _install_fake_anthropic(monkeypatch)
     provider = AnthropicProvider("sk-x", model="claude-sonnet-4-6", timeout_s=60, max_retries=2)
 
-    result = asyncio.run(provider.agenerate("prompt", max_tokens=100))
+    # _build_client() doğrudan test et — cache bypass — AsyncAnthropic constructor'ı yakala
+    client = provider._build_client()
 
-    assert isinstance(result, ProviderResult)
+    assert isinstance(client, _FakeAsyncClient)
     kw = _FakeAsyncClient.captured
     assert kw["max_retries"] == 2
     assert isinstance(kw["timeout"], httpx.Timeout)
     # httpx.Timeout(60) → tüm fazlar 60s
     assert kw["timeout"].read == 60
 
 
 def test_defaults_are_bounded(monkeypatch):
     """Varsayılanlar da sınırlı olmalı — timeout/retry hiç 'sonsuz' kalmamalı."""
     _install_fake_anthropic(monkeypatch)
     provider = AnthropicProvider("sk-x")
-    asyncio.run(provider.agenerate("p", max_tokens=10))
+
+    # _build_client() doğrudan test et — cache bypass
+    provider._build_client()
+
     kw = _FakeAsyncClient.captured
     assert isinstance(kw["timeout"], httpx.Timeout)
     assert kw["timeout"].read is not None and kw["timeout"].read > 0
     assert isinstance(kw["max_retries"], int) and kw["max_retries"] >= 1
```
