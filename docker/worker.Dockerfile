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
# CPU-only torch + остальной ml-стек ставятся ОДНОЙ командой, и оба
# индекса доступны pip-resolver-у с самого начала. CPU-индекс — primary,
# PyPI — extra: pip предпочтёт CPU wheel (2.6.x+cpu) для torch, а
# для остальных пакетов пойдёт на PyPI.
#
# Почему в один шаг: с раздельными `pip install` второй вызов не знал бы
# про CPU-индекс. Если pyproject.toml-constraint или транзитивные deps
# когда-нибудь заставят pip-resolver переустановить torch, он подтянет
# дефолтный wheel с PyPI вместе с nvidia-cublas/cudnn/cufft (~3 GB
# CUDA-балласта), и сборка падает на VPS с "No space left on device".
#
# Нижняя граница 2.6 — обязательна. transformers с CVE-2025-32434 блокирует
# `torch.load` на старых версиях, и загрузка checkpoint-ов с pytorch_model.bin
# (как у DeepPavlov/rubert-base-cased) падает с ValueError. См.
# https://nvd.nist.gov/vuln/detail/CVE-2025-32434.
RUN pip install --upgrade pip \
 && pip install \
      --index-url https://download.pytorch.org/whl/cpu \
      --extra-index-url https://pypi.org/simple/ \
      "torch>=2.6" \
      -e ".[ml,dev]"

# ---- Runtime stage ---------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp \
    MPLCONFIGDIR=/tmp/.matplotlib \
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
