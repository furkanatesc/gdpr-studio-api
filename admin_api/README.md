# admin-api — Platform Admin (back-office) servisi

Cross-tenant **salt-okunur** kiracı görünürlüğü + rollup metrikler + amaç-sınırlı, audit-zorunlu,
salt-okunur **impersonation**. Ana tenant API'sinden **ayrı deploy birimi**, paylaşılan Postgres'e
**least-privilege `kvkk_admin_ro`** rolüyle bağlanır (yapısal olarak tenant verisi YAZAMAZ).

> ⚠️ **GA (production) açılışı hukuki artefaktlara bağlıdır.** `H5_LEGAL_READY=false` olduğu sürece
> gerçek-tenant impersonation 403'tür. Aşağıdaki §Hukuki GA-gate imzalanmadan canlıya alınmaz.

---

## 1. Topoloji (spec §10)

- **admin frontend** (Plan B, greenfield): doğrudan Cloudflare Pages / AWS — Vercel'e KONMAZ.
  Cloudflare WAF + Authenticated Origin Pull (AOP) **IP allow-list + mTLS'i burada** zorlar.
- **admin-api**: ana API host'una komşu (Railway → hedef AWS `eu-central`), **ayrı servis**.
- **Personel Supabase projesi region ∈ {EU, TR}** (tenant Supabase'den AYRI proje, ayrı `aud`,
  MFA/AAL2 zorunlu). `platform_audit_logs` / `platform_metrics_daily` aynı EU Postgres'inde.

## 2. DB rolleri + migration sahipliği (spec §4.1, §5)

- **Tek migrator = ana backend** (`start.sh` → `alembic upgrade head`). admin-api **migrate ETMEZ**;
  boot'ta beklenen head'i (`expected_migration_head`) **doğrular**, yoksa fail-closed (boot-loop).
  → admin-api deploy'u, ana backend migration'ının (0020) canlı olmasına **bağımlıdır** (yoksa
  `relation does not exist`).
- Migration `0020_platform_admin` (owner `kvkk` / `MIGRATION_DATABASE_URL` ile) şunları yaratır:
  - `kvkk_admin_ro` — `LOGIN NOSUPERUSER **NOBYPASSRLS** NOCREATEDB NOCREATEROLE`; `SELECT` (tüm public
    tablolar + default-priv), `platform_audit_logs`/`impersonation_sessions` `INSERT`,
    `impersonation_sessions(ended_at,end_kind,approved_by)` kolon-sınırlı `UPDATE`,
    `UPDATE/DELETE` platform_audit_logs'ta **REVOKE** (append-only).
  - `kvkk_metrics_job` — aynı least-privilege; `platform_metrics_daily` `INSERT,UPDATE`.
- **Prod'da rol şifreleri migration'daki placeholder'lardan (`kvkk_admin_ro`/`kvkk_metrics_job`)
  DEĞİŞTİRİLMELİ** (deploy kapısı) veya roller güçlü şifreyle ayrıca kurulmalı.

## 3. Environment değişkenleri (deploy kapıları — spec §10 §160)

| Değişken | Rol / amaç | Not |
|---|---|---|
| `ADMIN_DATABASE_URL` | `kvkk_admin_ro` bağlantısı | Least-privilege; bounded pool |
| `METRICS_JOB_DATABASE_URL` | `kvkk_metrics_job` bağlantısı | Rollup job için; ayrı rol |
| `ADMIN_SUPABASE_PROJECT_URL` (+ ayrı `aud`, JWKS) | Personel Supabase (EU/TR, MFA) | Tenant projesinden AYRI |
| `H5_LEGAL_READY` | Impersonation aktivasyon kapısı | **Varsayılan `false`** — §Hukuki GA-gate |
| `ADMIN_REDIS_URL` | Degrade rate-limiter (§4.3) | **Boş = limiter disabled**; prod'da SET edilmeli |
| `ADMIN_RATE_LIMIT_READ_PER_MIN` / `..._WRITE_PER_MIN` | Rate limitleri | Varsayılan 120 / 30, tunable |
| `EXPECTED_MIGRATION_HEAD` | Boot doğrulaması | `0020` (head değişince güncelle) |

## 4. Ağ / servis sertleştirme (spec §4.3)

- **IP allow-list + mTLS = infra katmanı** (Cloudflare WAF+AOP veya AWS Security Group). App **XFF'ye
  GÜVENMEZ**.
- **🔴 ZORUNLU DEPLOY GATE — trusted-hop IP (Task 10 review I2):** admin-api bir reverse-proxy
  (Railway/Cloudflare) arkasında çalışır. `AdminRateLimitMiddleware` istemci IP'sini yalnız
  `scope["client"]` (socket-peer) üzerinden alır (XFF spoof reddi — doğru ilke). AMA proxy arkasında
  `scope["client"]` **proxy'nin kendi adresi** olabilir → o zaman (a) per-admin rate-limit tek kovaya
  çöker, (b) `platform_audit_logs.ip` her eylemi proxy IP'sine yazar (adli olarak işe yaramaz).
  **Fix (uygulama değil, sunucu/infra katmanı):** ASGI sunucusunu güvenilir hop'u yeniden yazacak
  şekilde koştur —
  ```
  uvicorn admin_api.main:app --proxy-headers --forwarded-allow-ips=<trusted-proxy-CIDR>
  ```
  (yalnız güvenilir proxy CIDR'ı; asla `*` değil). **Deploy'da doğrula:** bir admin eyleminden sonra
  `platform_audit_logs.ip` = gerçek admin origin IP'si + rate-limit kovaları per-admin ayrışıyor.
- **Rate-limit degrade** (self-DoS önleme, `AdminRateLimitMiddleware`): `ADMIN_REDIS_URL` set VE Redis
  erişilebilirken per-IP sabit-pencere limiter. Redis **configured-ama-erişilemez** olduğunda:
  yazma/state-değiştiren uçlar **fail-closed 503**, salt-okuma uçları **local in-process fallback +
  alarm log**. `ADMIN_REDIS_URL` **boşsa limiter tamamen kapalı** (dev/test). Asıl exfil koruması =
  impersonation **hacim/satır tavanı** (§7), request-sayısı değil.

## 5. Rollup metrik job'ı (spec §8)

- `admin_api/metrics_job.py` — `METRICS_JOB_DATABASE_URL` (`kvkk_metrics_job`) ile. **Boot'ta DEĞİL,
  ayrı cron/scheduler** ile koşturulur (tek-koşucu güvencesi `pg_advisory_lock`). Cross-tenant canlı
  scan YOK — yalnız `platform_metrics_daily` rollup.
- **Alarm:** rollup-job-fail sessiz durmamalı (spec §12 — `retention_maintenance.py:29` istisna-yutma
  tuzağına dikkat); job başarısızlığı gözlemlenebilirliğe bağlanmalı.

## 6. Audit sink (spec §5, §14-H2)

- `platform_audit_logs` **append-only + hash-chain** (`prev_hash`/`row_hash`, `UPDATE/DELETE` REVOKE).
- **WORM sink (deploy kapısı):** object-lock S3 / ayrı log hesabı — owner audit-DELETE artığını
  tespit-edilebilir kılar (kabul-edilen-ve-izlenen residual).
- **Saklama (H2, GA-gate):** `platform_audit_logs` + `impersonation_sessions` için **tanımlı saklama
  süresi + zamanlanmış purge** — süresiz append-only KVKK-uyumsuz. (`retention_maintenance.py`
  genişletilecek — owner-run; şu an DEFERRED, spec §14-H2.)

## 7. ⚖️ Hukuki GA-gate (`H5_LEGAL_READY=true` ön-koşulları — spec §14, GA-öncesi ZORUNLU)

Bu artefaktlar imzalanana kadar bayrak `false` kalır (impersonation 403; metrik/kiracı-listesi muaf):
- **C1** — DPA operatör-erişim maddesi (zaman-sınırlı, salt-okunur destek erişimini yetkilendirir);
  `POST /admin/impersonation` talimat/ticket ref'ine bağlı.
- **C2** — Personel NDA/gizlilik bağı (`platform_admins.confidentiality_ack_at`); avukatlık sırrı
  (m.36, KVKK m.12/4). Ayrıcalıklı belge tiplerinin hariç/redakte değerlendirmesi.
- **C3** — Kiracıya şeffaflık: platform erişimi kiracının kendi `audit_logs`'una aynalanır (m.11 /
  Art.15) + oturum açılışında bildirim.
- **H3** — ROPA/VERBİS/aydınlatma metnine işlenir.
- **H4** — Özel-nitelikli veri erişiminde **dual-control ZORUNLU** (kodda: `scope=="ozel_nitelikli"`).
- **L4** — İhlal bildirim yolu (72s Kurul + veri sahibi) olay müdahale planına bağlı.

## 8. Test / CI — PG RLS lane (spec §11, **CI PG lane ŞART**)

SQLite RLS'i test etmez (bypass no-op). Admin RLS testleri **gerçek Postgres** + **owner** URL ister
(`ADMIN_RLS_TEST_DATABASE_URL`; testler owner ile seed edip `kvkk_admin_ro:kvkk_admin_ro@…`'a çevirir).
Tenant RLS testleri (`tests/test_rls.py`) ise `RLS_TEST_DATABASE_URL` = **kvkk_app** (NOBYPASSRLS) ister
— iki farklı rol gerektiği için **iki ayrı env var** (çakışmaz):
- `tests/admin/test_admin_migration_rls.py` — kvkk_admin_ro tenant-tablo yazamaz (bypass altında bile);
  default-priv SELECT; platform_audit append-only.
- `tests/admin/test_admin_tenants_rls.py` — single-org list/detail RLS altında (begin_provisioning /
  set_org_context sıra doğruluğu).
- `tests/admin/test_admin_impersonation_rls.py` — bypass-off assert; kolon-sınırlı UPDATE; **SEC-C2**
  aggregate-sonra-impersonate aynı bağlantıda yabancı satır DÖNMEZ (4 scope parametrize).

Koşum (ikisi tek pytest çağrısında):
```bash
RLS_TEST_DATABASE_URL=postgresql+psycopg://kvkk_app:kvkk_app@<host>:5432/kvkk \
ADMIN_RLS_TEST_DATABASE_URL=postgresql+psycopg://kvkk:<owner-pw>@<host>:5432/kvkk \
  .venv/bin/pytest -q
```
CI (`.github/workflows/ci.yml`) her iki var'ı da set eder → tenant + admin RLS lane'leri gerçek-PG'de
aynı adımda koşar (owner migration'ı ayrı adımda `alembic upgrade head` ile uygular).

## 9. Açık riskler / izleyen iş (spec §12, §13)

Read-replica (ağır analitik primary'yi kilitlemesin), backfill tarihsel derinlik, ve H5-sonrası ayrı
gerçek-ölçek denetimi (Membership tek-org UNIQUE, async üretim kuyruğu, her-boot reseed, Redis
fail-open — bkz. `app/redis_client.py` da aynı sticky-singleton şeklinde, düşük risk fail-open).
