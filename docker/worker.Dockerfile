# CustDevAI Celery worker with ML stack (Phase 3, FR-SENT-*, FR-TOP-*).
#
# Веса моделей (RuBERT ~700 MB, multilingual-e5-base ~470 MB) НЕ
# скачиваются при сборке образа — это запрещено .gitignore и неоправданно
# увеличивает размер слоя. Веса подтягиваются при первом запуске
# warmup() и кэшируются в /models (volume ml_models_cache из docker-compose).
# После этого можно выставить TRANSFORMERS_OFFLINE=1.

FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        build-essential libpq-dev git \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY apps /app/apps
# CPU-only torch ставится отдельно из официального PyTorch CPU-индекса.
# Это критично для production без GPU: дефолтные wheels тянут nvidia-cublas,
# nvidia-cudnn, nvidia-cufft и пр. — суммарно ~3 GB бесполезного балласта,
# из-за которого билд падал на 80 GB VPS с "No space left on device".
# После того как torch уже установлен, `pip install -e ".[ml,dev]"`
# увидит его и не будет переустанавливать.
RUN pip install --upgrade pip \
 && pip install --index-url https://download.pytorch.org/whl/cpu "torch>=2.2,<2.6" \
 && pip install -e ".[ml,dev]"

# ---- Runtime stage ---------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ML_MODEL_CACHE_DIR=/models \
    HF_HOME=/models \
    TRANSFORMERS_CACHE=/models \
    SENTENCE_TRANSFORMERS_HOME=/models

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 libgomp1 postgresql-client \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home -d /app app \
 && mkdir -p /models /var/lib/custdevai/backups \
 && chown -R app:app /models /var/lib/custdevai

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

USER app

CMD ["celery", "-A", "apps.worker.celery_app", "worker", "--loglevel=info", "--concurrency=1"]
