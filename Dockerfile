FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PYTHONPATH=/srv

WORKDIR /srv

# Bağımlılıklar (yerel paketi kurmadan kaynaktan çalıştırırız → veri/alembic yolları sabit kalır)
# NOT: pyproject.toml [api] ile senkron tutulmalı (dep-layer cache için elle listeleniyor).
RUN pip install --no-cache-dir \
    "fastapi>=0.115" "uvicorn[standard]>=0.32" "pydantic>=2.7" "pydantic-settings>=2.5" \
    "sqlalchemy>=2.0" "alembic>=1.13" "psycopg[binary]>=3.2" "redis>=5.0" "anthropic>=0.40" \
    "sentry-sdk[fastapi]>=2.0"

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
