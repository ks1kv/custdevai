#!/usr/bin/env bash
# scripts/worker-run.sh — запуск pytest и другой ad-hoc нагрузки внутри
# одноразового worker-контейнера с примонтированными tests/ и
# pyproject.toml. Без этого пути pytest падает в production-образе:
# docker/worker.Dockerfile копирует только apps/, а USER app не имеет
# write в /app (см. docs/PRE_DEFENSE_RUNBOOK.md §1).
#
# Зачем отдельный скрипт, а не алиас в runbook'е: многострочный bash-
# alias с продолжением через '\' опасен при copy-paste — символы
# теряются, переменная остаётся пустой, и команда исполняется на хосте
# вместо контейнера.
#
# Использование:
#   ./scripts/worker-run.sh pytest -m ml ... -p no:cacheprovider -v -s
#   ./scripts/worker-run.sh python -c 'import torch; print(torch.__version__)'
#
# Опционально:
#   COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml" \
#       ./scripts/worker-run.sh ...
# По умолчанию используется dev-compose (только docker-compose.yml).

set -euo pipefail

if [[ $# -eq 0 ]]; then
    echo "usage: $0 <command> [args...]" >&2
    echo "       $0 pytest -m ml tests/ml/test_sentiment_quality.py -v" >&2
    exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILES="${COMPOSE_FILES:--f docker-compose.yml}"

# Пробрасываем в контейнер env-переменные, нужные ML-acceptance-тестам.
# `docker compose run -e VAR` без значения копирует значение из текущего
# окружения. Если переменная не задана — флаг безвреден.
ENV_ARGS=(
    -e PYTEST_CACHE_DIR=/tmp/.pytest_cache
    -e SENTIMENT_ASSERT_FR_07
    -e SENTIMENT_MODEL_PATH
    -e SENTIMENT_HOLDOUT_PATH
    -e HF_HOME
    -e TRANSFORMERS_CACHE
)

# shellcheck disable=SC2086
exec docker compose $COMPOSE_FILES run --rm \
    -v "${REPO_ROOT}/tests:/app/tests:ro" \
    -v "${REPO_ROOT}/pyproject.toml:/app/pyproject.toml:ro" \
    "${ENV_ARGS[@]}" \
    worker "$@"
