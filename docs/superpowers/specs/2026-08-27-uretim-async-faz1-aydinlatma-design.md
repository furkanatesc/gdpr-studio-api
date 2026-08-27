# Üretim uçları async — Faz 1: aydinlatma/generate (tasarım)

**Tarih:** 2026-08-27
**Bağlam:** Gerçek-ölçek boşluk denetimi #4 (async üretim). Karar: **Yaklaşım A — süreç-içi async**.
**İlgili:** `project-gercek-olcek-denetimi` (memory), `feedback-real-customer-scale`.

## 1. Sorun

Üretim uçları sync `def` + `StreamingResponse`; çekirdek `for delta in provider.stream(...)` →
`legal_core/provider.py` blocking `client.messages.stream`. FastAPI sync-generator'ı bir
threadpool thread'inde koşturur → **belge üretimi boyunca (saniyeler) bir thread tutulur.**
~40'lık threadpool dolunca TÜM sync uçlar (auth/billing/health) kuyruğa girer.

**Gerçek üretim uçları streaming:** 6 istemci-kapsamlı SSE ucu
(`/{client_id}/{aydinlatma|cerez|kayit|dpa|dpia|ihlal}/generate`). One-shot `/api/generate`
frontend'de kullanılmıyor. Bu yüzden gerçek starvation streaming yolunda.

## 2. Karar (kullanıcı, 2026-08-27)

- **Yaklaşım A (süreç-içi async):** yalnız provider ağ çağrısı `await`'e döner (AsyncAnthropic);
  prompt-üretimi + DB sync kalır. Yeni altyapı yok, interaktif+streaming UX korunur (YAGNI).
  B (iş kuyruğu + worker) ertelendi; Batch API elendi (interaktif değil).
- **DB stratejisi:** sync SQLAlchemy korunur. Async sınırı yalnız LLM çağrısı. Full
  async-SQLAlchemy migration YOK.
- **Fazlama:** **Faz 1 = aydinlatma/generate uçtan uca async** (tüm async-streaming desenini
  gerçek, kullanılan bir uçta kurar). Faz 2 = kalan 5 uç (mekanik tekrar) + opsiyonel one-shot.

## 3. Kapsam — Faz 1

**Sadece** aydinlatma yolu. Değişecekler:
1. `legal_core/provider.py` — `AnthropicProvider.astream` (+ `_aclient`, async Protocol).
2. `legal_core/generate.py` — `generate_aydinlatma_envanter_stream_async` (async generator).
3. `app/modules/aydinlatma.py` — `generate` → `async def`; `event_stream` → async generator.

**Değişmeyecekler:** sync `generate_aydinlatma_envanter_stream` ve `provider.stream` KALIR
(diğer 5 uç hâlâ onları kullanıyor; Faz 2'de dönüşecekler). Prompt-üretimi
(`build_aydinlatma_envanter_prompt`), `ensure_disclaimer`, grounding, DB repo'ları, kota/
idempotency mantığı aynen.

## 4. Tasarım

### 4.1 Provider — `astream`
`AnthropicProvider`'a async ikiz ekle (mevcut `stream`'in birebir semantiği):
```python
def _aclient(self):
    import httpx
    from anthropic import AsyncAnthropic
    return AsyncAnthropic(api_key=self._api_key,
                          timeout=httpx.Timeout(self._timeout_s),
                          max_retries=self._max_retries)

async def astream(self, prompt, *, max_tokens=DEFAULT_MAX_TOKENS):
    client = self._aclient()
    self.last_result = None
    async with client.messages.stream(model=self._model, max_tokens=max_tokens,
                                      messages=[{"role": "user", "content": prompt}]) as s:
        async for delta in s.text_stream:
            yield delta
        final = await s.get_final_message()
        usage = getattr(final, "usage", None)
        self.last_result = ProviderResult(text="", model=self._model,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            stop_reason=getattr(final, "stop_reason", None))
```
`last_result` (usage/stop_reason) sync yoldakiyle aynı sözleşmede doldurulur.

**Async Protocol:** `legal_core/provider.py`'ye `AsyncModelProvider(Protocol)` — `astream`.
Sync `ModelProvider` dokunulmaz (sync yol geriye uyumlu kalır).

### 4.2 legal_core — `generate_aydinlatma_envanter_stream_async`
Sync fonksiyonun birebir async ikizi; TEK fark `async for delta in provider.astream(...)`:
```python
async def generate_aydinlatma_envanter_stream_async(sections, boilerplate, profile, *,
                                                     provider, max_tokens=DEFAULT_MAX_TOKENS):
    yield ("grounding", [_section_to_grounding(s) for s in sections])
    prompt = build_aydinlatma_envanter_prompt(sections, boilerplate, profile)
    chunks = []
    async for delta in provider.astream(prompt, max_tokens=max_tokens):
        chunks.append(delta); yield ("delta", delta)
    streamed = "".join(chunks)
    final_text = ensure_disclaimer(streamed)
    if final_text != streamed:
        yield ("delta", final_text[len(streamed):])
    last = getattr(provider, "last_result", None)
    yield ("done", { ... sync ile birebir ... })
```
Aynı olay deseni: `('grounding', records) → ('delta', text)* → ('done', meta)`.

### 4.3 Endpoint — async `generate` + async `event_stream`
- `def generate(...)` → `async def generate(...)`. İmza/dep'ler AYNI (`tenant_session`,
  `enforce_generation_quota` sync dep'ler; FastAPI bunları threadpool'da koşturur — sorun yok).
- Pre-stream (sahiplik 404, `_claim_idempotency`, profile/boilerplate/sections, provider inşa)
  async route içinde inline sync — hepsi ms-ölçekli, `StreamingResponse` DÖNMEDEN önce çalışır.
- `def event_stream()` → `async def event_stream()`; iç döngü
  `async for kind, payload in generate_aydinlatma_envanter_stream_async(...)`.
- `StreamingResponse(event_stream())` — Starlette async generator'ı **event-loop'ta** iterler
  (threadpool thread'i TUTULMAZ) = fix'in özü.

### 4.4 DB mid-stream stratejisi (KRİTİK — semantik korunur)
Mevcut `event_stream` ilk `delta`'da DB'ye yazar (`GeneratedDocumentRepository.record` +
`reserve_generation_usage`) ve `done`'da usage'ı finalize eder. Bunlar **sync ve inline**
KALIR (hızlı tekil INSERT'ler; loop'u ms bloklar — kabul). **run_in_threadpool ile
SARMALAMA** — session başka thread'de yaratıldı; async generator'da sıralı tek-kullanıcı
olarak loop thread'inde kullanmak güvenli, ama iki thread'e taşımak SQLAlchemy session
thread-safety tehlikesi yaratır. Tek `await` = `provider.astream`. RLS GUC'lu bağlantı tüm
akış boyunca (şimdiki gibi) checkout kalır.

### 4.5 Hata & idempotency
Mevcut hata/`idempotency.release` semantiği AYNEN korunur (üretim başarısızsa kilit bırakılır;
warning-before-done sırası; kesik/reddedilen belge SAKLANMAZ + usage geri alınır). Async
generator'da `try/except/finally` sync yoldaki mantığın birebir kopyası olur.

## 5. Test stratejisi (TDD)

1. **Provider astream birim** (`tests/test_provider_astream.py`): AsyncAnthropic mock (kaçınılmaz
   mock — ağ). `astream` delta'ları akıtır + `last_result` usage/stop_reason doldurur.
2. **Core async parite** (`tests/test_generate_async_stream.py`): fake async provider ile
   `generate_aydinlatma_envanter_stream_async`, sync ikizle AYNI olay dizisini üretir
   (grounding→delta*→done), disclaimer eklenir.
3. **Endpoint async** (`tests/test_aydinlatma_api.py` migration): mevcut testler
   `generate_aydinlatma_envanter_stream`'i (sync) monkeypatch'liyor → **async fake generator**
   ile `generate_aydinlatma_envanter_stream_async`'i monkeypatch'e çevir. Kapsanan davranış
   (404-before-claim, olay sırası, audit 1×, kota rezervasyon/geri-alma, truncated/refusal
   uyarıları, idempotency) AYNEN geçmeli.

**Doğrulama:** pinli `.venv` (fastapi 0.141.1); ruff; CI (PG-lane) otorite. Yerelde PG-lane
takılır/skip — bkz `feedback-openapi-venv-regen`.

## 6. Faz 2 (outline — bu spec'in dışı)
Kalan 5 uç (cerez/kayit/dpa/dpia/ihlal) + generic `/api/generate(/stream)`: aynı desenin
mekanik tekrarı (her core `*_stream` fn'in async ikizi + endpoint async). Opsiyonel:
sync `stream`/`generate` + sync core fn'leri Faz 2 sonunda kaldır (yalnız async yol kalır).

## 7. Riskler & açık noktalar
- **Sync Session async route'ta:** sıralı tek-kullanıcı → güvenli; concurrency yok. Testlerle
  (mevcut aydinlatma suite) ve CI PG-lane ile doğrulanır.
- **AsyncAnthropic API yüzeyi:** `messages.stream` async context manager + `text_stream` async
  iterator + `await get_final_message()` — anthropic SDK'da mevcut (sync `stream`'in async ikizi).
- **StreamingResponse async generator:** Starlette native destekler.
- **Faz 1 tek uç:** diğer 5 uç Faz 2'ye kadar sync (threadpool) kalır — starvation tam
  kapanmaz, ama desen gerçek uçta kanıtlanır + en çok kullanılan uç (aydinlatma) önce düzelir.
