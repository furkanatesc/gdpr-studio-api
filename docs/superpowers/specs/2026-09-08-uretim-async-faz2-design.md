# Üretim async Faz 2 — tasarım spec'i (2026-09-08)

## Amaç
Faz 1 aydınlatma için async streaming yolunu kurdu (`AnthropicProvider.astream` +
`AsyncModelProvider` + `generate_aydinlatma_envanter_stream_async` + async endpoint).
Faz 2, kalan tüm belge üretim uçlarını aynı async yola taşır ve **sync yolu tamamen
kaldırır**. Böylece tek bir olay döngüsü altında eşzamanlı üretim gerçek-ölçekte
bloklamaz ([[feedback-real-customer-scale]]); ikili (sync+async) bakım yükü biter.

## Kapsam
Migre edilecek uçlar (hepsi bugün sync `def` + sync `for … in provider.stream(...)`):
- **cerez** (`app/modules/cerez.py`) — generic `generate_document_stream` kullanır.
- **kayit** (`app/modules/kayit.py`) — `generate_kayit_envanter_stream`.
- **dpia** (`app/modules/dpia.py`) — `generate_dpia_envanter_stream` (+`tetiklenenler`).
- **dpa generate** (`app/modules/dpa.py`) — `generate_dpa_envanter_stream` (+`processor`/`DpaScope`).
- **ihlal** (`app/modules/ihlal.py`) — `generate_ihlal_stream` (form-türevli, çift `bildirimTuru`, grounding YOK, kalıcılık YOK).
- **generic** (`app/modules/generation.py`) — `/api/generate/stream` (stream) + `/api/generate` (non-stream).
- **dpa review** (`legal_core/dpa_review.py`) — sync `provider.stream` toplayıcı, `run_in_threadpool` ile sarılı.

## Yaklaşım — Faz 1 desenini birebir tekrarla
Her streaming üreticinin gövdesi neredeyse aynı ince sarmalayıcı: `yield grounding;
prompt kur; for delta in provider.stream(...): yield ('delta',…); disclaimer kuyruğu;
yield ('done', meta)`. Async ikiz **mekanik** dönüşüm:
- `def` → `async def`, dönüş tipi `Iterator` → `AsyncIterator`,
- tek satır `for delta in provider.stream(...)` → `async for delta in provider.astream(...)`.
Prompt kurucular, grounding/scope hazırlığı, sayım/idempotency/audit/disclaimer mantığı
**değişmez** (sağlayıcıdan bağımsız, sync kalır). Endpoint `event_stream` `async def` olur,
`async for` ile ikizi sürer; mid-stream DB yazımları **inline sync** kalır (Faz 1'de
onaylanan tradeoff — thread pool / async DB YOK).

## Global kısıtlar
1. **Semantik korunur:** her uç için olay dizisi (grounding→delta*→done, ihlal'de
   grounding YOK), reservation/counting, idempotency claim/release (erken-hata + mid-stream),
   generated-document record + audit, discard-on-warning + reserve rollback, generic error
   SSE (Faz 1'de eklenen `classify_generation_error` dahil) — hepsi birebir taşınır.
2. **Sync yalnız EN SONDA silinir:** tüm uçlar + prompt testleri async'e geçmeden hiçbir
   sync sembol silinmez. Silme tek bir final task'ta.
3. **Testler pinli `.venv`** (`\.venv\Scripts\python.exe`) ile; sistem python
   `test_openapi_json_guncel`'i patlatır. `ruff check` de koşulur.
4. **Commit/PR'lara Claude atfı YOK** ([[feedback-no-coauthor-trailer]]): Co-Authored-By,
   Claude-Session, "Generated with Claude Code" — hiçbiri.
5. **ihlal özel:** çift `bildirimTuru` (kurul/ilgili_kisi) prompt seçimi + grounding'siz
   olay dizisi + kalıcılık-yok (audit-only success dalı) async ikizde ve endpoint'te aynen korunur.
6. **dpa review kararı:** `review_dpa`/`_collect_stream` `astream`'e çevrilir ve
   `run_in_threadpool` kaldırılır (dpa sync yoldan tamamen çıksın diye).
7. **`/api/generate` (non-stream) kararı:** `generate_document` (`provider.generate`,
   Faz 1 precedent'i yok) — ya async ikiz (`agenerate`) verilir ya uç emekliye ayrılır;
   sync `generate` silinebilmesi için karar plan'da netleştirilir.

## Sync silme sonrası silinecekler (final task)
`AnthropicProvider.stream` + `generate` + `_client` + sync `ModelProvider` Protocol;
tüm sync üreticiler (`generate_document`, `generate_document_stream`,
`generate_aydinlatma_envanter_stream`, `generate_kayit/dpia/dpa_envanter_stream`,
`generate_ihlal_stream`); `dpa_review` sync toplayıcı. Doğrulama: kalan `.stream(` /
`provider.generate(` referansı ve `ModelProvider` import'u YOK.

## Test deseni (Faz 1'den)
Sync doc-type testleri (`test_<type>_api.py`) sync `_fake_stream` + sync patch hedefi +
`_generate` doğrudan çağrı kullanır. Async'e geçiş: `_fake_stream` → `async def`, patch
hedefi → `_async` fn, `_generate` → `asyncio.run(mod.generate(...))`. Prompt testleri
(`test_*_prompt.py`) sync üreticiyi çağırdığından, ilgili sync üretici silinmeden ÖNCE
async ikize (ya da saf prompt-builder testine) repoint edilir (Wave C).

İlgili: [[project-gercek-olcek-denetimi]] · Faz 1 spec `2026-08-27-uretim-async-faz1-aydinlatma-design.md`.
