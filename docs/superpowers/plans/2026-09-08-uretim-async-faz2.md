# Üretim async Faz 2 — implementasyon planı (2026-09-08)

Spec: `docs/superpowers/specs/2026-09-08-uretim-async-faz2-design.md`
Referans: Faz 1 (aydınlatma) — merged, main. Async provider (`AnthropicProvider.astream`,
`AsyncModelProvider`) ZATEN VAR ve paylaşılır.

## Global Constraints (her task'a bağlayıcı)
- **Semantik korunur:** olay dizisi (grounding→delta*→done; ihlal'de grounding YOK),
  reservation/counting, idempotency claim/release (erken-hata + mid-stream), generated-doc
  record + audit, discard-on-warning + reserve rollback, generic error SSE
  (`classify_generation_error(e)` dahil — main'de #78 ile geldi). Async ikiz sync ile
  BİREBİR aynı, tek fark `async def`/`async for … provider.astream`.
- **Mid-stream DB inline sync** kalır (thread pool / async DB YOK — Faz 1 tradeoff'u).
- **Sync sembol yalnız EN SON task'ta silinir** (T8). Öncesinde hiçbir sync fn silinmez.
- **Testler pinli `.venv\Scripts\python.exe`** ile (sistem python `test_openapi_json_guncel`
  patlatır) + `ruff check`.
- **Commit/PR atfı YOK:** Co-Authored-By / Claude-Session / "Generated with Claude Code" YOK.
- Test deseni: `test_<type>_api.py` sync `_fake_stream`→`async def`, patch hedefi→`_async`,
  `_generate`→`asyncio.run(mod.generate(...))`. Faz 1 `test_aydinlatma_api.py` şablonu.

## Ruling'ler (plan)
- **R1 — `/api/generate` (non-stream):** emekliye AYRILMAZ; async ikiz eklenir
  (`AnthropicProvider.agenerate` + `generate_document_async`). Gerekçe: endpoint silmek
  kırıcı API değişikliği; async ikiz eklemek non-breaking. Yanlışsa maliyet: kullanılmayan
  bir ucu async yaptık (ölü kod), silmek kolay.
- **R2 — dpa review:** `review_dpa`/`_collect_stream` `astream`'e çevrilir, `run_in_threadpool`
  kaldırılır (T3'te). Gerekçe: dpa sync yoldan tamamen çıksın, aksi halde sync `stream` T8'de
  silinemez. Yanlışsa maliyet: review davranışı sync ile aynı kalmalı (testle doğrulanır).

## Görevler

### Task 1 — kayit async (şablon doğrulaması) [haiku]
- `legal_core/generate.py`: `generate_kayit_envanter_stream_async` ekle — `:248`'deki sync
  ikizin BİREBİR async'i (`async def`, `AsyncIterator`, `async for delta in provider.astream(...)`).
  Sync `generate_kayit_envanter_stream` KALIR.
- `app/modules/kayit.py`: `generate` → `async def`; provider `AnthropicProvider` aynı; iç
  `event_stream` (varsa) `async def`, `for` → `async for … _async`; import sync→async fn.
  Diğer her şey (canonicalize, measures/rules, reservation, audit, disclaimer) aynen.
- `tests/test_kayit_api.py`: `_fake_stream`→`async def`, patch hedefi `generate_kayit_envanter_stream_async`,
  `_generate`→`asyncio.run(kayitmod.generate(...))`. `test_kayit_prompt.py`'a DOKUNMA (Wave C/T7).
- Koş: `\.venv\Scripts\python.exe -m pytest tests/test_kayit_api.py -q` + ruff. Yeşil olmalı.

### Task 2 — dpia async [haiku]
- `generate_dpia_envanter_stream_async` (`:295` async ikizi; `tetiklenenler` positional arg aynen).
- `app/modules/dpia.py`: `generate` → `async def` + `async for`; sync import→async. `prepare` sync KALIR.
- `tests/test_dpia_api.py` async'e. `test_dpia_prompt.py`/`test_dpia_necessity.py`/`test_dpia_scoring.py` DOKUNMA.
- Koş: `pytest tests/test_dpia_api.py -q` + ruff.

### Task 3 — dpa generate async + review astream [sonnet]
- `generate_dpa_envanter_stream_async` (`:340` async ikizi; `processor`/`DpaScope` argları aynen).
- `app/modules/dpa.py`: `generate` → `async def` + `async for`; sync import→async.
- **dpa review (R2):** `legal_core/dpa_review.py` `_collect_stream` (`:169`) `astream`'e çevir
  (`async def`, `async for`); `review_dpa` async yap; `app/modules/dpa.py:420` `run_in_threadpool`
  sarmasını kaldır, doğrudan `await review_dpa(...)`. `dpa.review` zaten `async def`.
- `tests/test_dpa_api.py` async'e; `tests/test_dpa_review.py` + `tests/test_dpa_review_api.py`
  async fake'e (review artık astream). `test_prompt_dpa.py`/`test_dpa_scope.py`/`test_scoring_dpa.py` DOKUNMA.
- Koş: `pytest tests/test_dpa_api.py tests/test_dpa_review.py tests/test_dpa_review_api.py -q` + ruff.

### Task 4 — generic `generate_document_stream_async` + cerez async [sonnet]
- `legal_core/generate.py`: `generate_document_stream_async` — generic `:86` sync ikizin async'i
  (paylaşılan altyapı; T6 da kullanır). Sync `generate_document_stream` KALIR.
- `app/modules/cerez.py`: `generate` → `async def`; `generate_document_stream` → `_async` (`async for`).
  Form-türevli GenerateRequest kurulumu aynen.
- `tests/test_cerez_api.py` async'e (patch hedefi `generate_document_stream_async`).
- Koş: `pytest tests/test_cerez_api.py -q` + ruff.

### Task 5 — ihlal async (en zor) [sonnet]
- `generate_ihlal_stream_async` (`:383` async ikizi) — **çift `bildirim_turu` (kurul/ilgili_kisi)
  prompt seçimi + grounding OLAYI YOK (yalnız delta*→done)** aynen korunur.
- `app/modules/ihlal.py`: `generate` → `async def` + `async for` (grounding branch yok); sync import→async.
  Success dalı audit-only (kalıcılık YOK) aynen; `bildirimTuru` validasyonu aynen.
- `tests/test_ihlal_api.py` async'e. `test_ihlal_logic.py` DOKUNMA (Wave C/T7).
- Koş: `pytest tests/test_ihlal_api.py -q` + ruff.

### Task 6 — generic endpoint'ler async (`/api/generate/stream` + `/api/generate`) [sonnet]
- `app/modules/generation.py`: `/api/generate/stream` (`:256`) → `async def` + `async for` ile
  T4'ün `generate_document_stream_async`'i. `/api/generate` (non-stream, `:188`) → **R1**:
  `AnthropicProvider.agenerate` (AsyncAnthropic `messages.create`, sync `generate` `:79` async ikizi) +
  `legal_core/generate.py` `generate_document_async` (`:49` async ikizi) ekle; endpoint `async def`.
- Paylaşılan testler: `tests/test_generation_stream_billing.py`, `test_generation_idempotency.py`,
  `test_generation_stream_error_logging.py`, `test_generation_records_doc.py`, `test_generate.py`
  → async fake'e (bu uçlar artık async). `test_provider_astream.py` zaten async.
- Koş: `pytest tests/test_generation_stream_billing.py tests/test_generation_idempotency.py tests/test_generation_stream_error_logging.py tests/test_generation_records_doc.py tests/test_generate.py -q` + ruff.

### Task 7 — prompt testlerini async ikizlere repoint et (silmeye hazırlık) [haiku]
- `test_aydinlatma_prompt.py`, `test_kayit_prompt.py`, `test_dpia_prompt.py`, `test_prompt_dpa.py`,
  `test_ihlal_logic.py` — sync üreticiyi çağıran her yeri async ikize (async fake + `asyncio.run`)
  ya da saf prompt-builder testine repoint et. Amaç: hiçbir test artık sync üreticiye bağlı değil.
- Koş: yukarıdaki prompt testlerini pinli venv ile koştur + ruff.

### Task 8 — sync yolu SİL + doğrula [sonnet]
- `legal_core/provider.py`: `stream` (`:98`), `generate` (`:79`), `_client` (`:68`), sync
  `ModelProvider` Protocol (`:35`) SİL.
- `legal_core/generate.py`: tüm sync üreticiler SİL — `generate_document` (`:49`),
  `generate_document_stream` (`:86`), `generate_aydinlatma_envanter_stream` (`:154`),
  `generate_kayit_envanter_stream` (`:248`), `generate_dpia_envanter_stream` (`:295`),
  `generate_dpa_envanter_stream` (`:340`), `generate_ihlal_stream` (`:383`).
- `legal_core/dpa_review.py`: sync `_collect_stream` kalıntısı SİL (T3'te astream'e geçti).
- Doğrula: `grep -rn "\.stream(\|provider.generate(\|ModelProvider\b" legal_core app` → yalnız
  `astream`/`AsyncModelProvider` kalmalı; sync sembol referansı SIFIR. `__init__` export'ları temizle.
- Koş: **TAM suite** pinli venv + ruff temiz.

## Bağımlılıklar / sıra
T1→T2→T3→T4→T5 (tip-başına bağımsız ama sıralı yürütülür; T4 generic twin'i T6 için üretir).
T6 T4'e bağlı. T7 T1–T6 sonrası. T8 EN SON (tüm uçlar + prompt testleri async). Final
whole-branch review (opus) → PR. **MERGE = KULLANICI** (büyük değişiklik).
