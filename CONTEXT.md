# CustDevAI — контекст разработки

Этот файл обновляется в конце каждой фазы. Содержит сводку сделанного, ключевые архитектурные решения и список вопросов/задач для следующей фазы.

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
