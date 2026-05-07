# CustDevAI — контекст разработки

Этот файл обновляется в конце каждой фазы. Содержит сводку сделанного, ключевые архитектурные решения и список вопросов/задач для следующей фазы.

---

## Phase 2 — Telegram bot (завершена)

### Что сделано

1. **Модель Consent + миграция 0002.** Таблица `consents(id, session_id UNIQUE, granted_at, ip_address_hash, consent_version)` для FR-BOT-01 (явное согласие, № 152-ФЗ); поле `users.researcher_telegram_chat_id BIGINT NULL` для push-уведомлений (FR-BOT-09).
2. **aiogram-dispatcher с RedisStorage.** `apps/bot/dispatcher.py`: TTL FSM-state = 48 часов (FR-BOT-05), namespace `bot_fsm`. FSM-states: `AWAITING_CONSENT → IN_INTERVIEW → COMPLETED|INTERRUPTED`, плюс `IN_INTERVIEW_LONG_ANSWER` для FR-BOT-08.
3. **Deep-link парсер** (`apps/bot/deeplink.py`): `c<campaign_id>` без HMAC; защита через `Campaign.status == RUNNING`.
4. **`/start` handler** (`apps/bot/handlers/start.py`): создаёт сессию через `begin_session()`, telegram_id хешируется через `hash_telegram_id()` с per-campaign salt (FR-BOT-10, FR-DB-03). Resume-сценарий поддерживается (повторный `/start` с тем же telegram_id возвращает к текущему вопросу).
5. **Согласие** (`apps/bot/handlers/consent.py`): callback на inline-кнопку «✅ Согласен», `record_consent()` с `INSERT ... ON CONFLICT DO NOTHING` на UNIQUE(session_id) — двойное нажатие идемпотентно.
6. **ACID-приём ответа** (`apps/bot/services/interview_service.py:accept_answer`): `INSERT answer + UPDATE sessions.progress_count` в одном `async with db.begin()` (FR-DB-02). `ON CONFLICT DO NOTHING` на UNIQUE(session_id, question_id) защищает от повторного update от Telegram (FR-API-08).
7. **Длинные ответы** (FR-BOT-08): чанки накапливаются в FSM-data, склейка через `\n` после нажатия inline-кнопки «✅ Готово».
8. **Отказ от non-text** (FR-BOT-04): `apps/bot/handlers/interview.py` и `apps/bot/handlers/reject.py` отвечают «Принимаю только текст», state не меняется.
9. **`/stop`** (FR-BOT-06): `mark_interrupted()` → `status=INTERRUPTED`, ответы НЕ удаляются.
10. **Завершение** (FR-BOT-07): `mark_completed()` после ответа на последний вопрос, отправка `COMPLETED_MESSAGE`, очистка FSM-state.
11. **Уведомление исследователю** (FR-BOT-09 первый этап): `notify_service.maybe_notify_researcher_all_completed()` шлёт push при `count_active_in_campaign == 0`. Если `chat_id` не зарегистрирован — лог-skip.
12. **Webhook endpoint** (`apps/api/routers/webhook.py`): `POST /api/v1/telegram/webhook` (FR-API-03). Валидирует `X-Telegram-Bot-Api-Secret-Token` против `TELEGRAM_WEBHOOK_SECRET` (NFR-SEC-06), парсит Update вручную (`Request` → `Update.model_validate(body)`) и форвардит в lazy-init dispatcher.
13. **Реальный bot main.py** (`apps/bot/main.py`): заменяет stub Phase 1. В dev — `dp.start_polling`; в prod — `bot.set_webhook` + `asyncio.Event().wait()`, FastAPI обрабатывает входящие.
14. **Тесты.** 35 новых тестов (4 unit + 10 integration + остальные косвенно через Settings/общие фикстуры). Покрытие 61.88% (≥ 60% NFR-MNT-01).

### Закрытые требования Phase 2

| Группа | Полностью | Частично | Отложено |
|---|---|---|---|
| FR-BOT-01..10 | 01, 02, 03, 04, 05, 06, 07, 08, 10 | 09 (структура push-а есть, реальная доставка зависит от регистрации chat_id — Phase 4) | — |
| FR-API-03 | ✓ webhook endpoint с secret-token | — | — |
| FR-API-08 | ✓ ON CONFLICT DO NOTHING + UNIQUE(session_id, question_id) | — | — |
| FR-DB-02 | ✓ ACID INSERT+UPDATE в одной транзакции | — | — |
| FR-DB-03 | ✓ hash_telegram_id, per-campaign salt | — | — |
| NFR-SEC-06 | ✓ webhook secret в env | — | — |
| NFR-SEC-08 | ✓ согласие зафиксировано | — | — |
| NFR-COR-02 | ✓ question_id хранится | — | — |

### Открытые задачи для Phase 3

1. **Celery-задачи ML-анализа.** После `mark_completed()` всех сессий нужно поставить в очередь `analyze_campaign(campaign_id)`. Сигнал доходит из `interview_service.handle_answer` или из `notify_service` (когда уже знаем, что active=0).
2. **Второй этап push-уведомления (FR-BOT-09 завершение).** После окончания ML-анализа — отдельный push «Анализ готов, отчёт по ссылке».
3. **48-часовой sweeper.** Celery-beat-таск каждые 15 минут: `UPDATE sessions SET status='interrupted' WHERE status='active' AND last_activity_at < now() - 48h`. Минимально, ~30 строк.
4. **Транзакционность вокруг отправки сообщения Telegram.** Сейчас порядок: commit БД → отправить bot.answer(). Если bot.answer() упал, ответ в БД сохранён, респондент не увидел подтверждения — на повторный вопрос ответит → ON CONFLICT защитит. ОК для Phase 2, но в Phase 5 стоит добавить outbox-pattern для надёжной доставки.
5. **Регистрация `users.researcher_telegram_chat_id`** через web-UI исследователя — Phase 4. До этого notify_service всегда skip-ит push.

---

## Phase 1 — Foundation (завершена)

### Что сделано

1. **Скелет проекта.** Каталоги `apps/{api,bot,worker}`, `alembic/`, `docker/`, `tests/{unit,integration}`, `scripts/db/init/`, `.github/workflows/`. Собраны заглушки бот-сервиса и Celery-worker — печатают в лог `[bot]/[worker] not yet implemented`, контейнер живёт на `asyncio.Event().wait()`.

2. **PostgreSQL-схема.** 12 таблиц нормализованных до 3NF (FR-DB-01), 4 native ENUM-а (`campaign_status`, `session_status`, `sentiment_label`, `audit_action`), B-Tree индексы под FR-DB-04. Одна Alembic-ревизия `0001_initial_schema.py` создаёт всё разом и seed-ит 4 роли RBAC. SQLAlchemy 2.x в async-режиме.

3. **JWT + RBAC.** Access 15 мин / refresh 7 дней (FR-AUTH-04), bcrypt cost ≥ 12 (FR-AUTH-03 / NFR-SEC-02), Redis deny-list для отозванных jti, whitelist для refresh с ротацией. Брутфорс 5/10/15 (FR-AUTH-08). RFC 7807 ошибки на русском (FR-API-02).

4. **CRUD.** `/api/v1/auth/{login,refresh,logout}`, `/api/v1/users/*` (admin-only), `/api/v1/scripts/*` (с вопросами), `/api/v1/campaigns/*`. Пагинация limit/offset, default 50, max 100 (NFR-PRF-03). Все маршруты с префиксом `/api/v1` (FR-API-06).

5. **OpenAPI.** `/api/docs`, `/api/redoc`, `/api/openapi.json` защищены JWT (FR-API-07).

6. **HTTPS-enforcement.** В production-режиме `RequireHTTPSMiddleware` отказывает HTTP-запросам (NFR-SEC-01). В dev/staging — без ограничения.

7. **CLI bootstrap.** `python -m apps.api.cli create-admin --email --password` создаёт первого администратора (FR-AUTH-01) и пишет audit-запись `user_created`.

8. **Псевдонимизация Telegram ID.** Утилита `derive_campaign_salt` (HKDF-Expand) и `hash_telegram_id` (SHA-256, 32 байта) готовы (FR-DB-03 / NFR-SEC-08). Per-campaign соль `os.urandom(32)` записывается в `campaigns.pseudonym_salt` при создании кампании.

9. **Тесты.** 54 теста: 26 unit + 28 integration. Покрытие 72.74% по `apps/api/` — выше требуемых 60% (NFR-MNT-01). Интеграционные тесты гоняются на in-memory SQLite через `aiosqlite` с патчем `compiles(BigInteger, "sqlite")` → `INTEGER` для совместимости.

10. **Docker.** `docker/api.Dockerfile` (multi-stage `python:3.11-slim` + uvicorn + healthcheck `/health`), `docker/bot.Dockerfile` и `docker/worker.Dockerfile` — заглушки на Phase 1. Сервис `web` в `docker-compose.yml` закомментирован до Phase 4. Все контейнеры запускаются под user app (uid=10001).

11. **CI.** `.github/workflows/ci.yml` — проверка отсутствия закоммиченных `.env*` (NFR-SEC-06), ruff lint+format, mypy (continue-on-error на Phase 1), pytest с coverage --fail-under=60.

### Принятые архитектурные решения

См. `docs/ARCHITECTURE.md`. Ключевые:
- Слоистая архитектура router→service→repository, зависимости через FastAPI Depends.
- Ротация refresh-токенов через Redis whitelist (вместо хранения пар в БД).
- Hard DELETE сценария + 409 при наличии любых кампаний (без soft-delete).
- ENUM PostgreSQL native; `audit_log.ip_address` через `INET().with_variant(String, "sqlite")` для тестов.
- Per-campaign соль генерируется CSPRNG при создании кампании; HKDF-деривация — для случаев воспроизводимой соли в Phase 2 (восстановление сессии).
- LoggingEmailNotifier для FR-AUTH-06 на Phase 1; SMTPEmailNotifier — Phase 5.

### Закрытые требования

| Группа | Закрыто полностью | Закрыто частично | Отложено |
|---|---|---|---|
| FR-API-01..08 | 01, 02, 06, 07 | 03, 04, 05 (каркас, реализация — фазы 2–4), 08 (UNIQUE на answers) | — |
| FR-AUTH-01..08 | 01, 02, 03, 04, 05, 07, 08 | 06 (без реальной email-отправки) | — |
| FR-DB-01..08 | 01, 03, 04, 06 | 02, 05 (готовы; реальные транзакции — фазы 2/3); 08 (через docker volume) | 07 (delete-by-subject — Phase 5) |
| NFR-SEC-01..09 | 01, 02, 03, 04, 05, 06, 07 | 08 (псевдонимизация готова, compliance — после Phase 2) | 09 (актуально для ML-модулей — Phase 3) |
| NFR-PRF-01..08 | 03, 08 | 06, 07 (требует нагрузочных тестов Phase 5) | 01, 02, 04, 05 (бот, веб, ML) |
| NFR-MNT-01..05 | 01, 02, 03, 04, 05 | — | — |
| NFR-OPS-01..08 | 01, 02, 06 | 03..05, 07, 08 | — |
| NFR-COR-01..02 | 02 | 01 (применимо к ML — Phase 3) | — |
| NFR-REL-01..07 | 02 | — | 01, 03..07 (после prod-деплоя) |

### Открытые вопросы и задачи для Phase 2

1. **Aiogram FSM:** какой storage — Redis или Memory? В плане — Redis (через `RedisStorage`). Подключить к существующему redis-контейнеру.
2. **Согласие на обработку № 152-ФЗ:** где хранить — отдельная таблица `consents`, поле в `sessions`, или audit-запись? Скорее `consents(session_id, granted_at, version)`.
3. **Транзакционность приёма ответа (FR-DB-02):** одна транзакция на INSERT answer + UPDATE sessions.progress_count + Telegram-ответ. Какой паттерн при сбое отправки? Outbox.
4. **Webhook vs polling:** в `.env.example` есть `TELEGRAM_WEBHOOK_URL` (пусто → long-polling). Нужно решить, какой режим в production по умолчанию.
5. **Идемпотентность приёма (FR-API-08):** Telegram update_id или хеш текста? UNIQUE(session_id, question_id) уже есть в схеме, но повторное сообщение пользователя на тот же вопрос может быть легитимной правкой ответа.
6. **Отзыв всех refresh-токенов пользователя (FR-AUTH-07: «принудительный отзыв администратором»).** Нужно добавить таблицу/Redis-set `revoked_user_jtis:{user_id}` или поле `tokens_invalid_before TIMESTAMPTZ` в `users`. Интегрируется в `decode_token`.

### Команды для следующей фазы

```bash
# Локальный запуск
cp .env.example .env
docker-compose up --build

# Применить миграции
docker-compose exec api alembic upgrade head

# Создать первого админа
docker-compose exec api python -m apps.api.cli create-admin \
  --email admin@example.com --password Test12345!

# Тесты
pytest -m "not ml"
ruff check . && ruff format --check .
```

---

## Phase 2 — Telegram bot (планируется)

См. CLAUDE.md §6. Кратко: aiogram 3.x, webhook + long-polling режимы, FSM dialog, Redis state storage, `/stop`, асинхронный 48-часовой pause-and-resume, явное согласие № 152-ФЗ.
