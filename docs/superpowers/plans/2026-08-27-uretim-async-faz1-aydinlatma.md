# Üretim async — Faz 1 (aydinlatma) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `aydinlatma/generate` SSE ucunu uçtan uca async'e çevir; LLM çağrısı thread tutmadan `await` edilsin (threadpool starvation'ı bu uçta kapat).

**Architecture:** Yaklaşım A (süreç-içi async): yalnız provider ağ çağrısı async olur (AsyncAnthropic `astream`); prompt-üretimi + tüm DB işleri sync kalır. Endpoint + `event_stream` + core stream fn'in async ikizleri eklenir; sync ikizler diğer 5 uç için KALIR (Faz 2).

**Tech Stack:** FastAPI/Starlette (async `StreamingResponse`), `anthropic` SDK `AsyncAnthropic`, SQLAlchemy (sync, dokunulmaz), pytest + `asyncio.run`.

**Spec:** `docs/superpowers/specs/2026-08-27-uretim-async-faz1-aydinlatma-design.md`

## Global Constraints

- **Testler pinli `.venv` ile:** `.venv/Scripts/python.exe -m pytest ...` (fastapi 0.141.1). Sistem python DEĞİL (`test_openapi_json_guncel` sürüm-drift'ten patlar).
- **`ruff check .` temiz** olmalı (pytest'e ek).
- **Sync yol korunur:** `AnthropicProvider.stream` ve `generate_aydinlatma_envanter_stream` SİLİNMEZ/DEĞİŞMEZ (Faz 2'ye kadar diğer 5 uç kullanıyor).
- **Semantik korunur:** olay sırası (`grounding→delta*→done`), mid-stream `record`+`reserve`, `done`'da `settle`, warning-before-done, kesik/reddedilende discard+release, başarıda audit+store, hata'da `idempotency.release` — HEPSİ aynen.
- **Mid-stream DB sync inline:** `run_in_threadpool` ile SARMALAMA (cross-thread session tehlikesi). Tek `await` = provider akışı.
- **Commit trailer YOK** (Co-Authored-By eklenmez).

---

### Task 1: `AnthropicProvider.astream` + async Protocol

**Files:**
- Modify: `legal_core/provider.py` (mevcut `stream`'in altına async ikiz + `_aclient`; `ModelProvider` yanına `AsyncModelProvider`)
- Test: `tests/test_provider_astream.py` (Create)

**Interfaces:**
- Produces: `AnthropicProvider.astream(self, prompt: str, *, max_tokens: int) -> AsyncIterator[str]` (async generator); yürütme sonunda `self.last_result: ProviderResult` (usage + stop_reason) dolar. `AsyncModelProvider(Protocol)` — `astream`.

- [ ] **Step 1: Failing test yaz** — `tests/test_provider_astream.py`

```python
import asyncio
from types import SimpleNamespace

from legal_core.provider import AnthropicProvider


class _FakeTextStream:
    def __init__(self, deltas):
        self._deltas = deltas

    def __aiter__(self):
        async def gen():
            for d in self._deltas:
                yield d
        return gen()


class _FakeStreamCM:
    def __init__(self, deltas, usage, stop_reason):
        self.text_stream = _FakeTextStream(deltas)
        self._final = SimpleNamespace(
            usage=SimpleNamespace(input_tokens=usage[0], output_tokens=usage[1]),
            stop_reason=stop_reason,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get_final_message(self):
        return self._final


class _FakeAsyncClient:
    def __init__(self, cm):
        self.messages = SimpleNamespace(stream=lambda **kw: cm)


def test_astream_deltalari_akitir_ve_last_result_doldurur(monkeypatch):
    p = AnthropicProvider("sk-fake", model="claude-x")
    cm = _FakeStreamCM(["Ay", "dinlatma"], usage=(11, 22), stop_reason="end_turn")
    monkeypatch.setattr(p, "_aclient", lambda: _FakeAsyncClient(cm))

    async def _run():
        return [d async for d in p.astream("PROMPT", max_tokens=100)]

    deltas = asyncio.run(_run())

    assert deltas == ["Ay", "dinlatma"]
    assert p.last_result.input_tokens == 11
    assert p.last_result.output_tokens == 22
    assert p.last_result.stop_reason == "end_turn"
    assert p.last_result.model == "claude-x"
```

- [ ] **Step 2: Testin fail ettiğini gör**

Run: `.venv/Scripts/python.exe -m pytest tests/test_provider_astream.py -q`
Expected: FAIL — `AttributeError: 'AnthropicProvider' object has no attribute '_aclient'` / `astream`.

- [ ] **Step 3: Minimal implementasyon** — `legal_core/provider.py`, `stream` metodunun hemen altına ekle:

```python
    def _aclient(self):
        """Async Anthropic istemcisi (lazy import: legal_core saf kalır)."""
        import httpx
        from anthropic import AsyncAnthropic

        return AsyncAnthropic(
            api_key=self._api_key,
            timeout=httpx.Timeout(self._timeout_s),
            max_retries=self._max_retries,
        )

    async def astream(self, prompt: str, *, max_tokens: int = DEFAULT_MAX_TOKENS):
        """stream()'in async ikizi: metin delta'larını akıtır, bitince last_result'ı doldurur."""
        client = self._aclient()
        self.last_result = None
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
```

`ModelProvider` Protocol tanımının hemen altına async protokol ekle (dosyanın başında `Iterator` importu var; `AsyncIterator` ekleme GEREKMEZ — Protocol imzasında `...` kullanılıyor):

```python
@runtime_checkable
class AsyncModelProvider(Protocol):
    def astream(self, prompt: str, *, max_tokens: int = DEFAULT_MAX_TOKENS): ...
```

- [ ] **Step 4: Testin geçtiğini gör**

Run: `.venv/Scripts/python.exe -m pytest tests/test_provider_astream.py -q`
Expected: PASS

- [ ] **Step 5: ruff + commit**

```bash
.venv/Scripts/python.exe -m ruff check legal_core/provider.py tests/test_provider_astream.py
git add legal_core/provider.py tests/test_provider_astream.py
git commit -m "legal_core: AnthropicProvider.astream (AsyncAnthropic) + AsyncModelProvider"
```

---

### Task 2: `generate_aydinlatma_envanter_stream_async` (legal_core)

**Files:**
- Modify: `legal_core/generate.py` (mevcut `generate_aydinlatma_envanter_stream`'in hemen altına async ikiz)
- Test: `tests/test_generate_async_stream.py` (Create)

**Interfaces:**
- Consumes: bir provider nesnesi (Task 1 semantiği) — `astream(prompt, *, max_tokens) -> AsyncIterator[str]` + `last_result`/`model`.
- Produces: `async def generate_aydinlatma_envanter_stream_async(sections, boilerplate, profile, *, provider, max_tokens=DEFAULT_MAX_TOKENS) -> AsyncIterator[tuple[str, Any]]`; olay dizisi `('grounding', records) → ('delta', text)* → ('done', meta)` (sync ikizle birebir).

- [ ] **Step 1: Failing test yaz** — `tests/test_generate_async_stream.py`

```python
import asyncio

from legal_core.generate import generate_aydinlatma_envanter_stream_async
from legal_core.prompt import DISCLAIMER_MARKER
from legal_core.provider import ProviderResult


class FakeAsyncProvider:
    """Ağ yok: prompt'u yakalar, sabit delta'lar akıtır, last_result doldurur."""

    def __init__(self, text="Aydinlatma metni govdesi"):
        self._text = text
        self.model = "fake-model"
        self.last_result = None
        self.seen_prompt = None

    async def astream(self, prompt, *, max_tokens=8000):
        self.seen_prompt = prompt
        for ch in [self._text[:5], self._text[5:]]:
            yield ch
        self.last_result = ProviderResult(
            text="", model="fake-model", input_tokens=10, output_tokens=20, stop_reason="end_turn"
        )


def _collect(sections, boilerplate, profile, provider):
    async def _run():
        return [ev async for ev in generate_aydinlatma_envanter_stream_async(
            sections, boilerplate, profile, provider=provider, max_tokens=8000)]
    return asyncio.run(_run())


def test_async_stream_olay_dizisi_ve_disclaimer():
    provider = FakeAsyncProvider()
    events = _collect([], {}, None, provider)  # boş sections: grounding boş liste

    kinds = [k for k, _ in events]
    assert kinds[0] == "grounding"
    assert "delta" in kinds
    assert kinds[-1] == "done"
    # disclaimer akışta yoksa ('done' öncesi) bir delta olarak eklenir
    full = "".join(p for k, p in events if k == "delta")
    assert DISCLAIMER_MARKER in full
    done_meta = events[-1][1]
    assert done_meta["usage"] == {"inputTokens": 10, "outputTokens": 20}
    assert done_meta["stopReason"] == "end_turn"
    assert done_meta["model"] == "fake-model"
```

- [ ] **Step 2: Testin fail ettiğini gör**

Run: `.venv/Scripts/python.exe -m pytest tests/test_generate_async_stream.py -q`
Expected: FAIL — `ImportError: cannot import name 'generate_aydinlatma_envanter_stream_async'`.

- [ ] **Step 3: Minimal implementasyon** — `legal_core/generate.py`, sync `generate_aydinlatma_envanter_stream`'in hemen altına (aynı importlar/yardımcılar geçerli):

```python
async def generate_aydinlatma_envanter_stream_async(
    sections: list[Section],
    boilerplate: dict,
    profile: ClientProfile,
    *,
    provider: Any,  # astream() metoduna sahip bir AsyncModelProvider (duck-typed)
    max_tokens: int = DEFAULT_MAX_TOKENS,
):
    """generate_aydinlatma_envanter_stream'in async ikizi: TEK fark `async for provider.astream`."""
    yield ("grounding", [_section_to_grounding(s) for s in sections])

    prompt = build_aydinlatma_envanter_prompt(sections, boilerplate, profile)

    chunks: list[str] = []
    async for delta in provider.astream(prompt, max_tokens=max_tokens):
        chunks.append(delta)
        yield ("delta", delta)

    streamed = "".join(chunks)
    final_text = ensure_disclaimer(streamed)
    if final_text != streamed:
        yield ("delta", final_text[len(streamed):])

    last = getattr(provider, "last_result", None)
    yield (
        "done",
        {
            "model": getattr(provider, "model", "") or "",
            "disclaimer": DISCLAIMER,
            "usage": (
                {"inputTokens": last.input_tokens, "outputTokens": last.output_tokens}
                if last
                else None
            ),
            "stopReason": last.stop_reason if last else None,
        },
    )
```

- [ ] **Step 4: Testin geçtiğini gör**

Run: `.venv/Scripts/python.exe -m pytest tests/test_generate_async_stream.py -q`
Expected: PASS

- [ ] **Step 5: ruff + commit**

```bash
.venv/Scripts/python.exe -m ruff check legal_core/generate.py tests/test_generate_async_stream.py
git add legal_core/generate.py tests/test_generate_async_stream.py
git commit -m "legal_core: generate_aydinlatma_envanter_stream_async (sync ikizin async varyantı)"
```

---

### Task 3: Endpoint async + test-harness migration (`aydinlatma`)

**Files:**
- Modify: `app/modules/aydinlatma.py` (import + `generate` → `async def` + `event_stream` → async)
- Modify: `tests/test_aydinlatma_api.py` (fake stream'ler → async; doğrudan çağrılar → `asyncio.run`; monkeypatch hedefi → `_stream_async`)

**Interfaces:**
- Consumes: `generate_aydinlatma_envanter_stream_async` (Task 2).
- Produces: `async def generate(...) -> StreamingResponse` (aynı imza/dep'ler; artık coroutine döner).

- [ ] **Step 1: Import'u değiştir** — `app/modules/aydinlatma.py:25`

```python
from legal_core.generate import generate_aydinlatma_envanter_stream_async
```
(Sync `generate_aydinlatma_envanter_stream` importunu KALDIR — bu modül artık yalnız async'i kullanıyor. Not: sync fn legal_core'da KALIR, sadece bu dosyada import edilmez.)

- [ ] **Step 2: Endpoint'i async yap** — `app/modules/aydinlatma.py`, `generate` fonksiyonu:

Değişiklikler (gövde AYNEN korunur, yalnız 3 satır):
1. `def generate(` → `async def generate(`
2. İç `def event_stream():` → `async def event_stream():`
3. `for kind, payload in generate_aydinlatma_envanter_stream(` → `async for kind, payload in generate_aydinlatma_envanter_stream_async(`

`event_stream` içindeki TÜM DB çağrıları (`GeneratedDocumentRepository(...).record/discard`, `reserve_/settle_/release_generation_*`, `record_audit`, `_store_generated_document`, `session.commit()`), `try/except`, `idempotency.release`, warning/settle mantığı ve `return StreamingResponse(event_stream(), ...)` **hiç değişmez** (sync inline kalır).

- [ ] **Step 3: Test fake'lerini async'e çevir + çağrıları sar** — `tests/test_aydinlatma_api.py`

`_fake_stream` ve varyantlarını (`_fake_stream_truncated` vb.) sync `def ... yield` yerine `async def ... yield` yap; `_capture_stream` gibi sync-yield sarmalayıcıları da `async def` + `async for`'a çevir. Örnek:

```python
async def _fake_stream(*a, **kw):
    yield "grounding", []
    yield "delta", "Aydinlatma"
    yield "delta", " metni"
    yield "done", {"model": "claude-x", "usage": {"inputTokens": 10, "outputTokens": 20}}
```

`_capture_stream` deseni:
```python
    async def _capture_stream(sections, boilerplate, profile, **kw):
        captured["max_tokens"] = kw.get("max_tokens")
        async for ev in _fake_stream():
            yield ev
```

`_generate` yardımcısını coroutine'i çalıştıracak şekilde güncelle (endpoint artık `async def`):
```python
def _generate(db_session, client_id, **overrides):
    body = aydmod.GenerateIn(sections=[aydmod.SectionIn(is_sureci="Ozluk", kategoriler=["Kimlik"])])
    kwargs = dict(session=db_session, identity=IDENT, x_anthropic_key=None, idempotency_key=None)
    kwargs.update(overrides)
    return asyncio.run(aydmod.generate(client_id=client_id, body=body, **kwargs))
```

TÜM monkeypatch hedeflerini değiştir: `monkeypatch.setattr(aydmod, "generate_aydinlatma_envanter_stream", ...)` → `monkeypatch.setattr(aydmod, "generate_aydinlatma_envanter_stream_async", ...)`.

`_consume(response)` DEĞİŞMEZ (zaten `async for chunk in response.body_iterator` + `asyncio.run`). 404-RAISE testleri (`_generate` çağrısı HTTPException fırlatmalı) `asyncio.run` içinden fırlayan exception'ı aynen yakalar — değişiklik gerekmez.

- [ ] **Step 4: aydinlatma suite'i koştur (davranış guard)**

Run: `.venv/Scripts/python.exe -m pytest tests/test_aydinlatma_api.py -q`
Expected: PASS (tüm mevcut davranış: 404-before-claim, olay sırası, audit 1×, kota rezervasyon/geri-alma, truncated/refusal uyarıları, idempotency, max_tokens tavanı).

- [ ] **Step 5: ruff + commit**

```bash
.venv/Scripts/python.exe -m ruff check app/modules/aydinlatma.py tests/test_aydinlatma_api.py
git add app/modules/aydinlatma.py tests/test_aydinlatma_api.py
git commit -m "app: aydinlatma/generate async (event-loop'ta stream, thread tutmaz) + test migration"
```

---

### Task 4: Tam suite + doğrulama

- [ ] **Step 1: İlgili + geniş suite** (pinli .venv)

Run: `.venv/Scripts/python.exe -m pytest tests/test_provider_astream.py tests/test_generate_async_stream.py tests/test_aydinlatma_api.py tests/test_generate.py tests/test_provider_stop_reason.py -q`
Expected: PASS (sync yol testleri de yeşil — `generate_document`/`stream` dokunulmadı).

- [ ] **Step 2: ruff tüm değişen dosyalar**

Run: `.venv/Scripts/python.exe -m ruff check .`
Expected: All checks passed.

- [ ] **Step 3: PR + CI (otorite: PG-lane)**

```bash
git push -u origin feat/uretim-async-faz1-aydinlatma
gh pr create --base main --title "app: üretim async Faz 1 — aydinlatma/generate (AsyncAnthropic astream)" --body "<özet + spec/plan linki>"
```
CI yeşil → **merge kullanıcı teyidi bekler** (dış-etkili adım).

## Self-Review (yazım sonrası)

- **Spec coverage:** Spec §4.1→Task1, §4.2→Task2, §4.3+§4.4+§4.5→Task3, §5 testler→Task1-3, §5 doğrulama→Task4. Faz 2 (§6) kapsam dışı (spec'te de öyle). ✓
- **Placeholder:** PR body'de `<özet>` — executor doldurur (spec/plan hazır). Kod adımlarında TODO yok. ✓
- **Tip tutarlılığı:** `astream`/`generate_aydinlatma_envanter_stream_async`/`last_result` adları Task1→2→3 boyunca tutarlı; `ProviderResult` alanları (input_tokens/output_tokens/stop_reason/model) mevcut modelle uyumlu. ✓
