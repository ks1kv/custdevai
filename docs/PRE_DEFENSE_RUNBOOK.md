# Pre-defense runbook (Selectel VPS)

Пошаговое руководство для выполнения 5 предзащитных задач из
`docs/DEPLOYMENT.md` §14 на боевом стенде. Все команды предполагают,
что развёртывание по `docs/DEPLOYMENT.md` §1–11 уже выполнено и сервис
работает: `docker compose ps` показывает `api`, `worker`, `bot`,
`postgres`, `redis`, `web` в состоянии `healthy`.

Дальше — пять блоков. Каждый замыкает один раздел в pre-defense
чек-листе.

| № | Задача | Требование | Ожидаемое время | Выход |
|---|---|---|---|---|
| 1 | Fine-tune RuBERT | FR-SENT-07 | 4–10 ч CPU | `ML_METRICS.md` |
| 2 | 4 нагрузочных сценария | NFR-PRF-01/02/04/05/06/08 | 30–60 мин суммарно | `LOAD_TEST_REPORT.md` |
| 3 | Замер RTO | NFR-REL-05 | 20–30 мин | `DISASTER_RECOVERY.md` §4 |
| 4 | Playwright × 3 браузера | FR-WEB-12, NFR-OPS-05 | 15–20 мин | `BROWSER_QA_REPORT.md` |
| 5 | Demo end-to-end | FR-BOT-*, FR-WEB-*, FR-RPT-* | 10 мин | смоук, скриншоты |

Перед стартом — переменные:

```bash
cd /home/custdev/custdevai
export COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml"
```

---

## 1. Fine-tune RuBERT (FR-SENT-07)

**Цель:** accuracy ≥ 0.75 и weighted F1 ≥ 0.73 на ≥ 200 размеченных
русскоязычных текстах.

### 1.1. Baseline-замер до fine-tune (опционально, для сравнительной
таблицы в `ML_METRICS.md` «baseline vs fine-tune»)

В репо лежит ручной holdout `tests/ml/data/sentiment_fallback_holdout.json`
(202 примера: 68 pos / 67 neu / 67 neg, без дубликатов). Он подхватывается
acceptance-тестом, если `rusentne_2023_holdout.json` ещё не создан.

```bash
docker compose $COMPOSE_FILES exec worker \
    pytest -m ml tests/ml/test_sentiment_quality.py::test_sentiment_meets_quality_targets -v -s
```

В stdout будет строка вида
`[FR-SENT-07] holdout_size=202, accuracy=0.XXX, f1_weighted=0.XXX`.
Без `SENTIMENT_ASSERT_FR_07=true` тест не падает — фиксирует только
числа.

Записать результат в `docs/ML_METRICS.md` → «Сравнение с baseline».

### 1.2. Запуск fine-tune

```bash
# Один прогон с дефолтными гиперпараметрами (epochs=3, batch=8, lr=2e-5).
# На CPU Selectel-инстанса 4 vCPU — ~6–10 часов.
docker compose $COMPOSE_FILES exec worker \
    python -m apps.ml.sentiment.training \
        --output /models/rubert-finetuned \
        --epochs 3 --batch-size 8 --lr 2e-5 --seed 42 \
        2>&1 | tee /var/log/custdevai/training_run1.log
```

Что записывается:

1. Веса + tokenizer → `/models/rubert-finetuned/` (том `ml_models`).
2. Holdout → `tests/ml/data/rusentne_2023_holdout.json` внутри
   worker-контейнера (≥ 200 примеров stratified split, seed=42).
   Скопировать на хост:
   `docker compose $COMPOSE_FILES cp worker:/app/tests/ml/data/rusentne_2023_holdout.json tests/ml/data/`.
3. Метрики → `/models/rubert-finetuned/metrics.json`.

### 1.3. Подключить новые веса к API/worker

В `.env`:

```env
SENTIMENT_MODEL_PATH=/models/rubert-finetuned
```

Перезапуск:

```bash
docker compose $COMPOSE_FILES restart api worker bot
```

### 1.4. Acceptance-замер (FR-SENT-07 ≥ 0.75 / ≥ 0.73)

```bash
docker compose $COMPOSE_FILES exec worker \
    env SENTIMENT_ASSERT_FR_07=true \
        SENTIMENT_MODEL_PATH=/models/rubert-finetuned \
        pytest -m ml tests/ml/test_sentiment_quality.py -v
```

Зелёный прогон = FR-SENT-07 закрыто.

### 1.5. Заполнить `docs/ML_METRICS.md`

Из `metrics.json` перенести в md:

- Размер train/holdout, баланс классов
- Accuracy, weighted F1, macro F1
- Per-class precision/recall/F1 + support
- Confusion matrix
- Длительность обучения (из лога training_run1.log)
- Hardware (вывод `lscpu` + `free -h`)

### 1.6. Если не сошлось — итерации (Q2 strategy)

```bash
# Прогон 2: ниже lr.
docker compose $COMPOSE_FILES exec worker \
    python -m apps.ml.sentiment.training --output /models/rubert-ft-r2 \
        --epochs 4 --batch-size 8 --lr 1e-5 --seed 42

# Прогон 3: длиннее max_length.
docker compose $COMPOSE_FILES exec worker \
    python -m apps.ml.sentiment.training --output /models/rubert-ft-r3 \
        --epochs 3 --batch-size 4 --lr 2e-5 --max-length 384 --seed 42
```

В `ML_METRICS.md` фиксировать **каждый** прогон, не подменять
прошлые числа.

---

## 2. Четыре нагрузочных сценария

Установить k6 на VPS (если не установлен):

```bash
sudo apt-get install -y gnupg2 ca-certificates
curl -fsSL https://dl.k6.io/key.gpg | sudo gpg --dearmor -o /usr/share/keyrings/k6-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update && sudo apt-get install -y k6
```

### 2.1. Сценарий 1 — Telegram-webhook 50 VU × 60 с (NFR-PRF-01, PRF-06)

```bash
export K6_API_BASE=https://custdevai.example.com
k6 run --vus 50 --duration 60s tests/load/scenario_1_bot_webhook.js \
    --out json=var/load/s1_$(date +%F).json
```

Проверка: `http_req_duration{p(95)} ≤ 3000ms`.

### 2.2. Сценарий 2 — ML-анализ 200 синтетических сессий (NFR-PRF-04)

```bash
docker compose $COMPOSE_FILES exec worker \
    env CELERY_TASK_ALWAYS_EAGER=true \
        python -m tests.load.scenario_2_ml_analyze --sessions 200 \
    | tee var/load/s2_$(date +%F).json
```

Проверка: поле `wall_time_s ≤ 600`.

### 2.3. Сценарий 3 — отчёт на 500 сессий (NFR-PRF-05)

```bash
docker compose $COMPOSE_FILES exec worker \
    python -m tests.load.scenario_3_report_500 --sessions 500 --format pdf \
    | tee var/load/s3_pdf_$(date +%F).json

docker compose $COMPOSE_FILES exec worker \
    python -m tests.load.scenario_3_report_500 --sessions 500 --format xlsx \
    | tee var/load/s3_xlsx_$(date +%F).json
```

Проверка: оба прогона `elapsed_s ≤ 30`.

### 2.4. Сценарий 4 — 1000 RPS GET /campaigns (NFR-PRF-02, PRF-08)

```bash
export K6_API_BASE=https://custdevai.example.com
export K6_API_TOKEN="$(curl -s -X POST $K6_API_BASE/api/v1/auth/login \
    -H 'Content-Type: application/json' \
    -d '{"email":"admin@...","password":"..."}' | jq -r .access_token)"

k6 run tests/load/scenario_4_api_read.js \
    --out json=var/load/s4_$(date +%F).json
```

Проверка: `http_req_duration{p(95)} ≤ 200ms`.

### 2.5. Заполнить `docs/LOAD_TEST_REPORT.md`

Из JSON-выводов перенести в md: p50/p95/p99, throughput, error rate,
CPU/RAM хоста на пике (через `docker stats --no-stream` параллельно).

---

## 3. Замер RTO (NFR-REL-05 ≤ 60 мин)

Цель — пройти процедуру `docs/DISASTER_RECOVERY.md` §3 на чистом
инстансе и засечь секундомер.

### 3.1. Создать второй VPS того же тарифа (или использовать staging)

```bash
# На staging-хосте, в чистом каталоге:
git clone https://github.com/ks1kv/custdevai.git custdevai-restore
cd custdevai-restore
cp /path/to/prod/.env .            # тот же конфиг
```

### 3.2. Скопировать последний бэкап с production

```bash
ssh prod "docker compose $COMPOSE_FILES exec -T postgres \
    ls -t /var/lib/custdevai/backups/" | head -1
# например custdevai_2026-05-17_03-00.dump

scp prod:/var/lib/custdevai/backups/custdevai_2026-05-17_03-00.dump ./backups/
```

### 3.3. Запустить таймер и выполнить процедуру §3 DR

```bash
START=$(date +%s)
docker compose $COMPOSE_FILES up -d postgres redis
sleep 10
docker compose $COMPOSE_FILES exec -T postgres \
    pg_restore -U custdev -d custdevai -j 4 --clean --if-exists \
    /var/lib/custdevai/backups/custdevai_2026-05-17_03-00.dump
docker compose $COMPOSE_FILES up -d api worker bot web
# smoke-тест: /health должен вернуть 200
curl -fsS https://restore.custdevai.example.com/health
END=$(date +%s)
echo "RTO_seconds=$((END-START))"
```

### 3.4. Заполнить `docs/DISASTER_RECOVERY.md` §4

```
| Дата       | Backup-размер | Кол-во таблиц | Длительность | RTO_target | Статус |
|---|---|---|---|---|---|
| 2026-05-XX | 120 MB        | 16            | 8 мин 42 с   | ≤ 60 мин   | passed |
```

---

## 4. Playwright × 3 браузера (FR-WEB-12, NFR-OPS-05)

На любом dev-хосте (или VPS со свободным RAM):

```bash
cd tests/e2e
npm install
npx playwright install --with-deps chromium firefox

export E2E_BASE_URL=https://custdevai.example.com
export E2E_LOGIN=admin@custdevai.example.com
export E2E_PASSWORD=...

npm test            # все три профиля сразу
npm run report      # HTML-отчёт в playwright-report/
```

Что собрать для `docs/BROWSER_QA_REPORT.md`:

- Скриншоты главного дашборда из каждого профиля
- Длительность прогона каждого профиля
- Список зафиксированных различий (если есть)
- Подтверждение: `scrollWidth ≤ clientWidth` на 1024×768

---

## 5. Demo end-to-end (для защиты)

Минимальный сценарий, который показывается комиссии:

1. **Исследователь:** заходит в SPA (`/login`), создаёт сценарий из 3
   вопросов, создаёт кампанию на основе сценария, копирует
   deeplink-URL в Telegram.
2. **Респондент:** открывает Telegram-deeplink, проходит интервью на
   3 вопроса. Один ответ — позитивный, второй — нейтральный, третий —
   негативный.
3. **Исследователь:** жмёт «Запустить анализ» → дожидается завершения
   Celery-таски (5–30 секунд при одной сессии).
4. **Открывает дашборд кампании:**
   - sentiment-распределение: 1 / 1 / 1
   - топ-темы: 1–3 кластера
5. **Скачивает PDF-отчёт** через `/api/v1/campaigns/{id}/reports?format=pdf`.

Скриншоты этих 5 шагов кладутся в `docs/demo/2026-05-XX/`.

---

## Чек-лист «всё закрыто»

- [ ] `docs/ML_METRICS.md`: accuracy ≥ 0.75, weighted F1 ≥ 0.73
- [ ] `docs/LOAD_TEST_REPORT.md`: 4 сценария, все passed
- [ ] `docs/DISASTER_RECOVERY.md` §4: одна строка с RTO ≤ 60 мин
- [ ] `docs/BROWSER_QA_REPORT.md`: 3 профиля × passed
- [ ] `docs/demo/<date>/`: 5 скриншотов end-to-end
- [ ] `docker compose ps`: все сервисы healthy
- [ ] `CONTEXT.md`: финальная сводка обновлена
