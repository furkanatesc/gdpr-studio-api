#!/bin/sh
# Prod başlangıç: migrate + seed'i RUNTIME container'da (env/DATABASE_URL kanıtlı çalışır)
# koştur, sonra uvicorn'a devret. Railway preDeployCommand sessizce çalışmadığı için
# (2026-08-07 keşfi: prod haftalarca seed'siz kaldı) buraya taşındı.
# set -e: migrate/seed patlarsa container BAŞLAMAZ → deploy LOUD fail eder, sessiz drift olmaz;
# Railway sağlık kontrolü eski sürümü canlı tutar (yeni sürüm serve etmez). Seed idempotent.
set -e

alembic upgrade head
python -m app.seed
python -m app.retention_maintenance
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
