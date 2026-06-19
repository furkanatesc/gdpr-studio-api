"""Model sağlayıcı soyutlaması — Claude birincil, sağlayıcı değiştirilebilir.

legal_core saf kalır: anthropic SDK yalnızca AnthropicProvider içinde lazy import
edilir. BYOK (kullanıcının kendi anahtarı) ve managed (sunucu anahtarı) yolları
aynı arayüzü kullanır — fark yalnızca hangi api_key'in geçtiğidir.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 8000


@dataclass(frozen=True)
class ProviderResult:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


@runtime_checkable
class ModelProvider(Protocol):
    def generate(self, prompt: str, *, max_tokens: int = DEFAULT_MAX_TOKENS) -> ProviderResult: ...


class AnthropicProvider:
    """Anthropic Claude implementasyonu (BYOK veya managed anahtar)."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        if not api_key:
            raise ValueError("api_key zorunludur (BYOK veya managed).")
        self._api_key = api_key
        self._model = model
        # stream() bittikten sonra final usage burada saklanır.
        self.last_result: ProviderResult | None = None

    @property
    def model(self) -> str:
        return self._model

    def generate(self, prompt: str, *, max_tokens: int = DEFAULT_MAX_TOKENS) -> ProviderResult:
        from anthropic import Anthropic  # lazy: legal_core'u saf tutar

        client = Anthropic(api_key=self._api_key)
        message = client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text
        usage = getattr(message, "usage", None)
        return ProviderResult(
            text=text,
            model=self._model,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
        )

    def stream(self, prompt: str, *, max_tokens: int = DEFAULT_MAX_TOKENS) -> Iterator[str]:
        """Metin delta'larını akıtır; bitince final usage'ı self.last_result'a yazar."""
        from anthropic import Anthropic

        client = Anthropic(api_key=self._api_key)
        self.last_result = None
        with client.messages.stream(
            model=self._model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        ) as s:
            yield from s.text_stream
            final = s.get_final_message()
            usage = getattr(final, "usage", None)
            self.last_result = ProviderResult(
                text="",
                model=self._model,
                input_tokens=getattr(usage, "input_tokens", 0) or 0,
                output_tokens=getattr(usage, "output_tokens", 0) or 0,
            )
