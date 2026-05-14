# Load testing — CustDevAI Phase 5

Сценарии нагрузочного тестирования для верификации NFR-PRF-01/02/04/05/06/08.

## Состав

| Файл | Цель | Покрывает |
|---|---|---|
| `scenario_1_bot_webhook.js` | 50 параллельных Telegram-сессий → p95 ≤ 3 с | NFR-PRF-01, NFR-PRF-06 |
| `scenario_2_ml_analyze.py` | ML-анализ 200 синтетических сессий за ≤ 10 мин | NFR-PRF-04 |
| `scenario_3_report_500.py` | Генерация PDF/XLSX на 500 сессий за ≤ 30 с | NFR-PRF-05 |
| `scenario_4_api_read.js` | 1000 RPS GET /campaigns → p95 ≤ 200 мс | NFR-PRF-02, NFR-PRF-08 |

`scenario_1_*` и `scenario_4_*` — k6 (JS). `scenario_2_*` и
`scenario_3_*` — Python (генерируют синтетические данные через
прямой insert и вызывают service-функции в eager-режиме).

## Стек

- **k6** (Grafana Labs) — для HTTP-нагрузки. Установка:
  `apt install k6` либо
  `wget https://github.com/grafana/k6/releases/download/v0.51.0/k6-v0.51.0-linux-amd64.tar.gz`.
- **Python** — для сценариев, требующих доступа к БД и Celery-таскам.

## Запуск

### k6 сценарии

```bash
# Локально (dev-стек на :8000)
export API_BASE=http://localhost:8000
export WEBHOOK_SECRET=$(grep TELEGRAM_WEBHOOK_SECRET .env | cut -d= -f2)
k6 run --vus 50 --duration 60s tests/load/scenario_1_bot_webhook.js
k6 run tests/load/scenario_4_api_read.js
```

`--out json=out.json` сохранит сырые метрики для последующей обработки.

### Python сценарии

```bash
# Загрузка 200 сессий + запуск ML-анализа (≤ 10 мин — NFR-PRF-04)
CELERY_TASK_ALWAYS_EAGER=true \
    python -m tests.load.scenario_2_ml_analyze --sessions 200

# Генерация отчёта на 500 сессий (≤ 30 с — NFR-PRF-05)
python -m tests.load.scenario_3_report_500 --sessions 500 --format pdf
```

Каждый python-сценарий печатает JSON-сводку с фактическими измерениями;
её копируем в `docs/LOAD_TEST_REPORT.md`.

## Запуск на production-стенде Selectel

После деплоя (см. `docs/DEPLOYMENT.md`) повторяем сценарии с
`API_BASE=https://<custdevai-domain>`. Для k6 нужна установка на
отдельной машине (или в Docker-контейнере), чтобы не создавать
самоконкуренцию ресурсов с системой.

## Результаты

Сводный отчёт со всеми измерениями: `docs/LOAD_TEST_REPORT.md`.
