# KVKK Yönetim — Backend

Faz 1: mikroservis-hazır modüler monolit. Şu an `legal_core` çekirdeği hazır;
sırada Postgres + Alembic ve FastAPI `/generate`.

## Yapı

```
backend/
├── legal_core/           # SAF çekirdek (IO yok) — worker.py/db_retriever.py evrimi
│   ├── normalize.py      # Türkçe-duyarlı normalize (NFC + I/ı)
│   ├── models.py         # API kontratı (web/lib/types.ts ile birebir, camelCase)
│   ├── grounding.py      # etiket → kategori çözümleme + envanter kayıtları
│   ├── rules.py          # GLOBAL_RULES + iş kuralı repo arayüzü
│   ├── prompt.py         # prompt kurulumu + disclaimer garantisi
│   ├── provider.py       # ModelProvider soyutlaması + AnthropicProvider (BYOK/managed)
│   ├── generate.py       # üretim orkestrasyonu
│   └── adapters.py       # JSON/dict repository'leri (test + masaüstü)
├── data/categories.json  # grounding kaynağı (Postgres'e seed edilir)
├── eval/                 # hukuki-doğruluk eval harness (golden set)
│   ├── cases.py          # temsili senaryolar + beklenen hukuki özellikler
│   ├── checks.py         # madde atfı / bölüm / m.6 / saklama-uydurma / disclaimer
│   └── runner.py         # skorlu rapor + exit code
├── tests/                # pytest — 20 test (normalize, grounding, generate, golden-grounding)
└── pyproject.toml
```

Veri erişimi (kategoriler, iş kuralları) ve model çağrısı **enjekte edilen arayüzlerle**
sağlanır; aynı çekirdek hem web (Postgres) hem masaüstü (JSON/SQLite) tarafında çalışır.

## Geliştirme

```bash
python -m venv .venv
./.venv/Scripts/python -m pip install -e ".[dev]"   # Windows
# veya: source .venv/bin/activate && pip install -e ".[dev]"
pytest -q
```

## Hukuki-doğruluk eval (golden set)

Prompt/model/grounding değişince üretilen dokümanların hukuki doğruluğunun regresyona
uğramadığını kanıtlar.

```bash
python -m eval.runner --grounding-only   # modelsiz, ücretsiz (grounding doğruluğu)
python -m eval.runner                     # tüm senaryolar, GERÇEK model (.env anahtarı gerekir)
python -m eval.runner aydinlatma_saglik   # tek senaryo
```

Kontroller: madde atıfları (KVKK/GDPR), zorunlu bölümler, **m.6 özel nitelikli veri
işlenişi**, **saklama süresi uydurma yasağı** (envanterde yoksa placeholder), zorunlu
disclaimer, grounding doğruluğu. Deterministik (grounding) kısmı `pytest`'te de koşar.

