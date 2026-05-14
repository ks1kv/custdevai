# Нагрузочное тестирование CustDevAI (NFR-PRF-01..08)

Документ агрегирует результаты нагрузочных сценариев, реализованных в
`tests/load/`. Целевые показатели — раздел 3.3.3 «Производительность»
требований ВКР.

## Целевые значения

| ID | Требование | Цель | Сценарий |
|---|---|---|---|
| NFR-PRF-01 | Отклик Telegram-бота на 50 сессиях | p95 ≤ 3 с | scenario_1 |
| NFR-PRF-02 | Загрузка веб-панели с 1000 записями | ≤ 3 с | scenario_4 (косвенно) |
| NFR-PRF-04 | ML-анализ кампании на 200 сессий | ≤ 10 мин | scenario_2 |
| NFR-PRF-05 | Генерация отчёта на 500 сессий | ≤ 30 с | scenario_3 |
| NFR-PRF-06 | 50 одновременных сессий без деградации | concurrency 50 | scenario_1 |
| NFR-PRF-08 | API read-запросы (1000 RPS) | p95 ≤ 200 мс | scenario_4 |

## Инфраструктура тестов

| Параметр | Значение |
|---|---|
| Сценарий 1 (k6, JS) | `tests/load/scenario_1_bot_webhook.js` |
| Сценарий 2 (Python, ML eager) | `tests/load/scenario_2_ml_analyze.py` |
| Сценарий 3 (Python, отчёт eager) | `tests/load/scenario_3_report_500.py` |
| Сценарий 4 (k6, JS) | `tests/load/scenario_4_api_read.js` |
| k6 install | `apt install k6` или бинарь Grafana Labs |
| Python deps | `.[ml]` extras для сценария 2 |

## Сценарий 1 — Webhook 50 параллельных сессий (NFR-PRF-01, NFR-PRF-06)

### Описание

50 виртуальных пользователей k6 по очереди постят update-ы (start →
consent → 5 ответов) на `/api/v1/telegram/webhook`. Каждое VU делает
полный цикл за ~7–10 секунд, итого через duration=60s — 300+ полных
интервью.

Замер: p95 от `http_req_duration` тегом `phase=webhook`.

### Команда запуска

```bash
export API_BASE=https://<custdevai-domain>
export WEBHOOK_SECRET=$(grep TELEGRAM_WEBHOOK_SECRET .env | cut -d= -f2)
export CAMPAIGN_ID=1
k6 run --vus 50 --duration 60s tests/load/scenario_1_bot_webhook.js
```

### Результаты

| Метрика | Значение | Цель | Статус |
|---|---|---|---|
| Полных интервью | _TBD_ | — | — |
| p50 latency | _TBD_ | — | — |
| p95 latency | _TBD_ | ≤ 3000 мс | _TBD_ |
| p99 latency | _TBD_ | — | — |
| error rate | _TBD_ | < 1% | _TBD_ |
| pg_stat_activity peak | _TBD_ | < pool_size | _TBD_ |

## Сценарий 2 — ML-анализ 200 сессий (NFR-PRF-04)

### Описание

Скрипт seed-ит синтетическую кампанию с 200 сессиями × 5 ответов
(итого 1000 ответов) с реалистичными русскоязычными текстами.
Затем вызывает `analyze_campaign(campaign_id)` в eager-режиме Celery,
замеряет wall-time от старта до записи `analysis_status=completed`.

### Команда запуска

```bash
docker compose exec api bash -lc \
  'CELERY_TASK_ALWAYS_EAGER=true python -m tests.load.scenario_2_ml_analyze --sessions 200'
```

### Результаты

| Метрика | Значение | Цель | Статус |
|---|---|---|---|
| Кол-во сессий | 200 | 200 | — |
| Wall-time | _TBD_ | ≤ 600 с | _TBD_ |
| Sentiment-обработано ответов | _TBD_ | 1000 | — |
| Найдено тем | _TBD_ | 5–15 | — |

## Сценарий 3 — Генерация отчёта на 500 сессий (NFR-PRF-05)

### Описание

Seed 500 сессий × 5 ответов (2500 answers), `ReportService.generate(...)`
с `CELERY_TASK_ALWAYS_EAGER` не нужен — отчёт строится синхронно через
`loop.run_in_executor`.

### Команда запуска

```bash
docker compose exec api python -m tests.load.scenario_3_report_500 --sessions 500 --format pdf
docker compose exec api python -m tests.load.scenario_3_report_500 --sessions 500 --format xlsx
```

### Результаты

| Формат | Wall-time | Размер файла | Цель | Статус |
|---|---|---|---|---|
| PDF | _TBD_ | _TBD_ КБ | ≤ 30 с | _TBD_ |
| XLSX | _TBD_ | _TBD_ КБ | ≤ 30 с | _TBD_ |

## Сценарий 4 — API read 1000 RPS (NFR-PRF-02, NFR-PRF-08)

### Описание

k6 в режиме `constant-arrival-rate` подаёт 1000 запросов/секунду на
`GET /api/v1/campaigns?limit=100` в течение 30 секунд после warm-up.
В БД предварительно создано ≥ 1000 кампаний.

### Подготовка БД

```bash
docker compose exec api python -m tests.load.scenario_3_report_500 \
    --sessions 0 --format pdf  # создаёт пустую кампанию-каркас
# повторить 1000 раз либо через bulk insert SQL
```

### Команда запуска

```bash
export API_BASE=https://<custdevai-domain>
export AUTH_TOKEN=$(curl -s -X POST $API_BASE/api/v1/auth/login \
    -d '{"email":"admin@example.com","password":"..."}' \
    -H 'Content-Type: application/json' | jq -r .access_token)
k6 run tests/load/scenario_4_api_read.js
```

### Результаты

| Метрика | Значение | Цель | Статус |
|---|---|---|---|
| RPS подано | _TBD_ | 1000 | — |
| RPS обработано | _TBD_ | ≥ 980 | _TBD_ |
| p50 latency | _TBD_ | — | — |
| p95 latency | _TBD_ | ≤ 200 мс | _TBD_ |
| p99 latency | _TBD_ | — | — |
| error rate | _TBD_ | < 1% | _TBD_ |

## Сводная таблица соответствия NFR-PRF

| Требование | Статус | Замер |
|---|---|---|
| NFR-PRF-01 | _TBD_ | scenario_1 p95 |
| NFR-PRF-02 | _TBD_ | scenario_4 (косвенно: 1000 записей в выдаче) |
| NFR-PRF-04 | _TBD_ | scenario_2 wall-time |
| NFR-PRF-05 | _TBD_ | scenario_3 wall-time |
| NFR-PRF-06 | _TBD_ | scenario_1 VUs=50 без error spike |
| NFR-PRF-08 | _TBD_ | scenario_4 p95 |

## План смягчения при провале

Если на текущем тире Selectel показатель не достигается — повышаем
тариф vertical scaling (больше vCPU / RAM), что не требует архитектурных
изменений и потому совместимо с NFR-MNT-03 (подменяемость реализаций).

Конкретные пороги повышения тира:

| Сценарий | Trigger | Тир (Selectel) |
|---|---|---|
| scenario_1 p95 > 3 с | api/bot worker CPU > 90% | 4 → 8 vCPU |
| scenario_2 > 10 мин | worker CPU 100% всё время | GPU-инстанс (Phase 6) |
| scenario_3 > 30 с | CPU > 80% во время рендера | 4 → 8 vCPU |
| scenario_4 p95 > 200 мс | asyncpg pool exhaustion | повысить `pool_size` в Settings или 4 → 8 vCPU |

## Воспроизводимость

Все сценарии используют фиксированный seed (`rng_seed=42` в helpers и
сценариях 1/4 через `--vus`/`--rate` — детерминистичные параметры).
Результаты прогона можно повторить, что важно для приёмки.
