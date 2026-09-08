"""Model sağlayıcı soyutlaması — Claude birincil, sağlayıcı değiştirilebilir.

legal_core saf kalır: anthropic SDK yalnızca AnthropicProvider içinde lazy import
edilir. BYOK (kullanıcının kendi anahtarı) ve managed (sunucu anahtarı) yolları
aynı arayüzü kullanır — fark yalnızca hangi api_key'in geçtiğidir.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

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
        """AsyncAnthropic ile tek-seferlik (stream'siz) üretim; await messages.create."""
        async with self._aclient() as client:
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

    def _aclient(self):
        """Async Anthropic istemcisi (lazy import: legal_core saf kalır)."""
        import httpx
        from anthropic import AsyncAnthropic

        return AsyncAnthropic(
            api_key=self._api_key,
            timeout=httpx.Timeout(self._timeout_s),
            max_retries=self._max_retries,
        )

    async def astream(self, prompt: str, *, max_tokens: int = DEFAULT_MAX_TOKENS) -> AsyncIterator[str]:
        """Metin delta'larını akıtır; bitince final usage'ı self.last_result'a yazar."""
        self.last_result = None
        async with self._aclient() as client:
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
