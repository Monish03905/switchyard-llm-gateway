# syntax=docker/dockerfile:1

# ---- cockpit -------------------------------------------------------------
FROM node:22-alpine AS cockpit
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ---- yard ----------------------------------------------------------------
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app
COPY requirements.txt requirements-postgres.txt ./
RUN pip install --no-cache-dir -r requirements-postgres.txt

COPY app ./app
COPY scripts ./scripts
COPY --from=cockpit /web/dist ./web/dist

RUN useradd --create-home --uid 10001 yard \
    && mkdir -p /data \
    && chown -R yard:yard /data
USER yard

# One process on purpose: the response cache, breaker, rate limiter, and chaos
# arming are in-memory. Scale with a bigger box, not more workers, unless you
# also move those pieces to Redis/Postgres.
ENV SERVE_FRONTEND=true \
    PROVIDER_MODE=auto \
    DATABASE_URL=sqlite+aiosqlite:////data/switchyard.db
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/health', timeout=3)"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
