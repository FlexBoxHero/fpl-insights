FROM node:20-alpine AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/
COPY packages/fpl_shared /app/packages/fpl_shared
COPY services/api /app/services/api
COPY services/etl /app/services/etl
COPY services/ml /app/services/ml
COPY scripts /app/scripts

RUN pip install --no-cache-dir \
    -e /app/packages/fpl_shared \
    -e /app/services/etl \
    -e /app/services/ml \
    -e /app/services/api

COPY --from=web /web/dist/web/browser /app/apps/web/dist/web/browser

ENV PYTHONPATH=/app/packages/fpl_shared/src:/app/services/api:/app/services/etl/src:/app/services/ml/src
ENV SPA_DIR=/app/apps/web/dist/web/browser
ENV PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["sh", "-c", "cd /app/packages/fpl_shared && alembic upgrade head && cd /app/services/api && uvicorn app.main:server --host 0.0.0.0 --port ${PORT:-8000}"]
