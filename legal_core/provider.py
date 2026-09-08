"""Model sağlayıcı soyutlaması — Claude birincil, sağlayıcı değiştirilebilir.

legal_core saf kalır: anthropic SDK yalnızca AnthropicProvider içinde lazy import
edilir. BYOK (kullanıcının kendi anahtarı) ve managed (sunucu anahtarı) yolları
aynı arayüzü kullanır — fark yalnızca hangi api_key'in geçtiğidir.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 8000
# Dayanıklılık varsayılanları: timeout/retry OLMADAN upstream asılırsa event loop +
# DB bağlantısı süresiz tutulur → istek yanıtsız kalır. Sınırlı timeout + az sayıda
# retry bunu keser.
DEFAULT_TIMEOUT_S = 60.0
DEFAULT_MAX_RETRIES = 2


@dataclass(frozen=True)
class ProviderResult:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    # Anthropic'in "stop_reason"u: "max_tokens" ise metin cumle ortasinda kesilmis
    # olabilir. None -> eski cagrilar (varsayilan) kirilmasin.
    stop_reason: str | None = None


@runtime_checkable
class AsyncModelProvider(Protocol):
    async def agenerate(self, prompt: str, *, max_tokens: int = DEFAULT_MAX_TOKENS) -> ProviderResult: ...

    def astream(self, prompt: str, *, max_tokens: int = DEFAULT_MAX_TOKENS): ...


class _AsyncClientCache:
    """Anahtar başına paylaşılan async model istemcilerinin sınırlı LRU önbelleği.

    Havuz reuse: aynı (api_key, timeout_s, max_retries) → aynı AsyncAnthropic (dolayısıyla
    aynı httpx bağlantı havuzu/keepalive). Her çağrıda yeni client + taze TLS handshake
    yerine yeniden kullanım. BYOK anahtarları sınırsız büyümesin diye maxsize; kapasite
    aşılınca EN ESKİ (LRU) client evict edilip aclose ile kapatılır. Süreç tek event
    loop'ta (uvicorn worker) çalıştığından ek kilit gerekmez.

    VARSAYIM (evict pinlemez): evict yalnız LRU-yaşına bakar, in-use refcount tutmaz. Aynı
    anda >maxsize DISTINCT (api_key,timeout,retries) BYOK anahtarı UÇUŞTA ise, hâlâ istek
    işleyen bir client evict+aclose edilip o istek kırılabilir. Managed anahtar daima MRU →
    fiilen pinli; bu risk yalnız aşırı BYOK çeşitliliğinde. Gerekirse maxsize artır / refcount ekle.
    """

    def __init__(self, maxsize: int = 32) -> None:
        self._cache: OrderedDict[tuple[Any, ...], Any] = OrderedDict()
        self._maxsize = maxsize

    async def get(self, key: tuple[Any, ...], factory: Callable[[], Any]) -> Any:
        client = self._cache.get(key)
        if client is not None:
            self._cache.move_to_end(key)  # LRU: dokunulan en yeni
            return client
        client = factory()
        self._cache[key] = client
        if len(self._cache) > self._maxsize:
            _, evicted = self._cache.popitem(last=False)  # en eski
            await evicted.aclose()
        return client

    async def aclose_all(self) -> None:
        clients = list(self._cache.values())
        self._cache.clear()
        for c in clients:
            await c.aclose()


# Modül-seviye havuz: aynı süreçteki tüm istekler paylaşır.
_CLIENT_CACHE = _AsyncClientCache()


async def aclose_all_clients() -> None:
    """Uygulama kapanışında (lifespan/shutdown) havuzdaki tüm async client'ları kapatır."""
    await _CLIENT_CACHE.aclose_all()


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
            raise ValueError("api_key zorunludur (BYOK veya managed).")
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
        """AsyncAnthropic ile tek-seferlik (stream'siz) üretim; await messages.create.

        Client havuzdan gelir (paylaşılan) — per-call KAPATILMAZ; havuz yaşamı boyunca
        yeniden kullanılır (kapanış aclose_all_clients ile)."""
        client = await self._aclient()
        message = await client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
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

    async def _aclient(self):
        """Havuzlanmış async Anthropic istemcisi — (api_key,timeout,retries) başına paylaşılır."""
        key = (self._api_key, self._timeout_s, self._max_retries)
        return await _CLIENT_CACHE.get(key, self._build_client)

    def _build_client(self):
        """Yeni AsyncAnthropic (lazy import: legal_core saf kalır). Yalnız cache-miss'te çağrılır."""
        import httpx
        from anthropic import AsyncAnthropic

        return AsyncAnthropic(
            api_key=self._api_key,
            timeout=httpx.Timeout(self._timeout_s),
            max_retries=self._max_retries,
        )

    async def astream(self, prompt: str, *, max_tokens: int = DEFAULT_MAX_TOKENS) -> AsyncIterator[str]:
        """Metin delta'larını akıtır; bitince final usage'ı self.last_result'a yazar.

        Client havuzdan gelir (paylaşılan) — per-call KAPATILMAZ; yalnız RESPONSE
        (messages.stream) kapatılır."""
        self.last_result = None
        client = await self._aclient()
        async with client.messages.stream(
            model=self._model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        ) as s:
            async for delta in s.text_stream:
                yield delta
            final = await s.get_final_message()
            usage = getattr(final, "usage", None)
            self.last_result = ProviderResult(
                text="",
                model=self._model,
                input_tokens=getattr(usage, "input_tokens", 0) or 0,
                output_tokens=getattr(usage, "output_tokens", 0) or 0,
                stop_reason=getattr(final, "stop_reason", None),
            )
