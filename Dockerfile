FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PYTHONPATH=/srv

WORKDIR /srv

# Bağımlılıklar (yerel paketi kurmadan kaynaktan çalıştırırız → veri/alembic yolları sabit kalır)
# fastembed HARİÇ (semantic fallback lazy + varsayılan kapalı); dev deps (pytest/ruff) HARİÇ.
#
# SÜRÜMLER SABİT (exact pin) — test edilen .venv baseline'ı ile birebir (reproducible build).
# NEDEN: daha önce ">=" tavansız pinler yüzünden her rebuild "en son"u çekiyordu; anthropic
# yeni bir majora atlayıp httpx yerine httpx2 kullanınca AsyncAnthropic(timeout=httpx.Timeout)
# prod'da TypeError verip TÜM üretimi düşürdü (bkz #82). Exact pin bu pin-drift sınıfını keser:
# prod = pytest'in geçtiği sürümler. Sürüm yükseltince .venv'i güncelle + tam suite koştur +
# buradaki pinleri `.venv` pip freeze ile senkronla. (İzleyen adım: tam lockfile/uv.)
RUN pip install --no-cache-dir \
    "fastapi==0.141.1" "uvicorn[standard]==0.49.0" "pydantic==2.13.4" "pydantic-settings==2.14.1" \
    "sqlalchemy==2.0.51" "alembic==1.18.4" "psycopg[binary]==3.3.4" "redis==8.0.0" "anthropic==0.109.2" \
    "sentry-sdk[fastapi]==2.63.0" "pyjwt[crypto]==2.13.0" "itsdangerous==2.2.0" "httpx==0.28.1" \
    "email-validator==2.3.0" "stripe==15.3.0" "openpyxl==3.1.5" "python-multipart==0.0.32" "python-docx==1.2.0"

COPY . .

EXPOSE 8000

CMD ["sh", "/srv/start.sh"]
