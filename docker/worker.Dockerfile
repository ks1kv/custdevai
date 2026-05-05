# CustDevAI Celery worker — заглушка для Phase 1 (без ML-стека).
# ML-зависимости подключаются в Phase 3 через build-arg или отдельный Dockerfile.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY apps /app/apps
RUN pip install --upgrade pip && pip install -e ".[dev]"

RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home app
USER app

CMD ["celery", "-A", "apps.worker.celery_app", "worker", "--loglevel=info", "--concurrency=1"]
