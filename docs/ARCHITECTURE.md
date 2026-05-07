# CustDevAI — архитектурные решения

Этот документ фиксирует ключевые архитектурные решения, принятые на Phase 1 (Foundation) и Phase 2 (Telegram bot), и обоснования за ними. Обновляется по мере развития системы.

## Phase 2 — решения по Telegram-боту

- **Прямой доступ бота к PostgreSQL** через общий `apps.api.db` и тот же async-engine. HTTP-прослойка между ботом и API отвергнута — она ломает FR-DB-02 (ACID INSERT answer + UPDATE sessions.progress_count в одной транзакции до отправки подтверждения респонденту). У бота отдельный `lru_cache`-singleton sessionmaker (5/10 пул) в `apps/bot/db.py`.
- **FSM в Redis с TTL 48 часов** через `aiogram.fsm.storage.redis.RedisStorage` под namespace `bot_fsm`. Состояние и data переживают рестарт контейнера (FR-BOT-05); namespace изолирует от refresh-tokens и brute-force-counters Phase 1.
- **Идемпотентность приёма ответа** через `INSERT ... ON CONFLICT DO NOTHING` на UNIQUE(session_id, question_id) из миграции 0001 (FR-API-08). Counter `progress_count` инкрементируется только при реальном INSERT; `last_activity_at` обновляется в обоих случаях, чтобы 48-часовое окно считалось от последнего реального действия пользователя.
- **DELETE сценария — hard, без soft-delete** (повтор Phase 1; здесь подтверждается, что на consents каскад от sessions работает корректно).
- **Согласие** через таблицу `consents` (UNIQUE на session_id, ip_address_hash, consent_version). Двойное нажатие кнопки обрабатывается тем же `INSERT ... ON CONFLICT DO NOTHING`. На Phase 2 ip_address_hash остаётся NULL — наполнится в Phase 5 после настройки reverse-proxy с `X-Forwarded-For`.
- **DELETE сценария при наличии завершённых сессий — 409** (см. Phase 1, не меняется). Для bot-flow это значит: даже если все сессии completed, сценарий нельзя удалить, пока есть кампании.
- **Webhook vs polling** выбирается на старте `apps/bot/main.py` по `settings.is_production && settings.telegram_webhook_url`. В webhook-режиме Telegram бьёт в `POST /api/v1/telegram/webhook` (FastAPI), который валидирует `X-Telegram-Bot-Api-Secret-Token` и форвардит update в lazy-init Dispatcher через `dp.feed_update()`. Bot и Dispatcher — singletons, переиспользуются между запросами. В webhook-handler-е принимаем raw `Request` (не типизированный `Update`), потому что `aiogram.types.Update` ломает `fastapi.openapi.get_openapi()` при сборке схемы.
- **Уведомление исследователю (FR-BOT-09)** — два этапа: на Phase 2 реальное «все сессии завершены» из `notify_service.maybe_notify_researcher_all_completed`; на Phase 3 второе «ML-анализ готов» в Celery-таске. Отдельный `Bot(token=settings.telegram_notify_bot_token or settings.telegram_bot_token)` создаётся per-call, закрывается в `finally`. Если `users.researcher_telegram_chat_id` NULL — лог-skip без падения (UI регистрации chat_id — Phase 4).
- **48-часовой sweeper отложен в Phase 5.** В Phase 2 — только FSM TTL в Redis. Сессии, зависшие в `active`, чистит sweeper при операционной доводке вместе с нагрузочными тестами.
- **Telegram ID** нигде в открытом виде не сохраняется (FR-BOT-10): только SHA-256 хеш с per-campaign salt из `apps/api/auth/hashing.py:hash_telegram_id`. В Redis FSM aiogram кладёт telegram_id в ключ — это допустимо, так как Redis внутренний и ключи эфемерные (TTL 48h).
- **48-часовой пользовательский опыт «Готово»** для длинных ответов (FR-BOT-08): inline-кнопка после каждого чанка, склейка через `\n` в FSM-data. Альтернатива «таймер тишины» отвергнута как недетерминированная.

---

## 1. Слоистая архитектура серверной части

Каждый сервис строится в три слоя:
1. **Presentation** — `apps/api/routers/*.py`, `apps/api/auth/router.py`. FastAPI-роутеры, парсинг входа, формирование ответа. Без бизнес-логики.
2. **Services** — `apps/api/services/*.py`, `apps/api/auth/service.py`. Оркестрация: транзакции, валидация инвариантов, побочные эффекты (email-уведомления, audit-логи).
3. **Repositories** — `apps/api/db/repositories/*.py`. Только SQL и маппинг. Не знают о HTTP.

Зависимости внедряются через FastAPI `Depends` (`apps/api/deps.py`). Это даёт `dependency_overrides` для тестов без monkeypatching.

## 2. ORM: SQLAlchemy 2.x async, 3NF, native ENUM

- Декларативный API `Mapped[...]` / `mapped_column(...)`.
- Naming convention в `MetaData` для предсказуемых имён ограничений и индексов (важно для Alembic).
- ENUM-ы PostgreSQL native (`campaign_status`, `session_status`, `sentiment_label`, `audit_action`) — типобезопасность на уровне БД.
- Composite PK для junction-таблиц (`user_roles`, `session_topics`) — экономит индекс и предотвращает дубли.
- `audit_log.ip_address` использует `INET` на Postgres и `String(45)` на SQLite через `with_variant` — нужно для интеграционных тестов на in-memory SQLite. На production это всегда INET.

## 3. Псевдонимизация Telegram ID (FR-DB-03)

Поле `campaigns.pseudonym_salt BYTEA(32) NOT NULL` хранит per-campaign соль. На Phase 1 соль генерируется через `os.urandom(32)` в `CampaignService.create()`. Утилита `derive_campaign_salt()` из `apps/api/auth/hashing.py` доступна для деривации соли через HKDF-Expand от `PSEUDONYM_MASTER_SALT` — будет использоваться ботом в Phase 2 при сценариях, где соль воспроизводимая (восстановление сессии). Хеширование `hash_telegram_id(tg_id, salt)` — SHA-256 над `salt || ascii(tg_id)`, на выходе 32 байта.

## 4. Аутентификация: JWT + Redis deny/whitelist

- Access-токен 15 минут, refresh-токен 7 дней (FR-AUTH-04).
- Каждый токен имеет уникальный `jti` (UUID4).
- Logout / refresh заносят jti в `revoked:{jti}` (Redis deny-list) с TTL = оставшееся время жизни токена.
- Refresh-токены ротируются: новый refresh после `/auth/refresh`, старый одновременно отзывается и удаляется из whitelist `refresh:{jti}`.
- Это даёт полную ротацию refresh без хранения пары access+refresh в БД.

Альтернатива — opaque-токены в БД — отвергнута: дороже по latency и сложнее масштабировать stateless-режим. Trade-off: при компрометации `JWT_SECRET` все ранее выданные access-токены становятся доверенными до их exp. Mitigation: ротация секрета + `revoked:*` ключи переживают рестарт Redis (AOF включён).

## 5. RBAC: 4 роли, decorators-style

Роли (`Admin`, `Researcher`, `Analyst`, `Respondent`) seed-вставляются в миграции 0001. Привязка пользователь→роль через `user_roles`. Список ролей кладётся в access-токен как claim `roles`, и проверяется FastAPI Depends-ом `require_roles(*Role)`. Такое решение исключает обращение к БД на каждый запрос (proven Read), но требует выписать новый access после изменения ролей.

## 6. Брутфорс-защита и rate-limit

- Алгоритм 5/10/15 (FR-AUTH-08): 5 неуспешных попыток за 10 минут → 15-минутный lock на IP.
- Реализация в Redis: `bf:{ip}` (счётчик с TTL 600 с) и `bf:lock:{ip}` (TTL 900 с).
- Идентификация IP — `X-Forwarded-For` (за reverse-proxy), иначе `request.client.host`.
- На уровне приложения возвращается 429 RFC 7807; `Retry-After` отправляется в Phase 5.

## 7. RFC 7807 ошибки на русском

Все ошибки API сериализуются через `apps/api/errors.py` в `application/problem+json` с обязательными полями `type, title, status, instance` и опциональными `detail, errors`. Все `title`/`detail` — на русском (FR-API-02). Стектрейсы из `_unhandled_handler` логируются, но не утекают в тело ответа (NFR-SEC-07).

## 8. DELETE сценария — hard, без soft-delete

`DELETE /api/v1/scripts/{id}` физически удаляет сценарий и каскадно — вопросы. Если на сценарий ссылается ЛЮБАЯ кампания (любого статуса) — 409 Conflict. Soft-delete отвергнут: вводит долг (фильтр `WHERE deleted_at IS NULL` в каждом SELECT) без выгоды на этапе MVP. Завершённые кампании сохраняют все данные ответов и анализа независимо от существования сценария.

## 9. Каскады удаления (FR-DB-06)

- `users → user_roles`: CASCADE.
- `users → scripts.created_by_user_id`: SET NULL + ручная переписка владельца на админа в `UserService.deactivate()`.
- `scripts → questions`: CASCADE.
- `scripts → campaigns`: RESTRICT (плюс приложение блокирует ещё в сервисе).
- `campaigns → sessions, topics`: CASCADE.
- `sessions → answers, session_topics`: CASCADE.
- `answers → sentiment_results`: CASCADE.

## 10. Конфигурация и секреты

`apps/api/config.py:Settings(BaseSettings)` читает все секреты только из ENV (`.env` в dev, secret-manager в prod). Валидация на старте: `BCRYPT_COST_FACTOR ≥ 12` (NFR-SEC-02), `JWT_SECRET` ≥ 32 символа, `PSEUDONYM_MASTER_SALT` ≥ 32 символа. Любая утечка секрета в `.env*` (кроме `.env.example`) блокируется CI-проверкой `git ls-files`.

## 11. Тестовая стратегия

- **Unit** (быстрые, без БД): pytest + `FakeAsyncRedis` (in-memory). Покрывают чистые модули — passwords, jwt, rbac, hashing, settings, problem-details, bruteforce.
- **Integration**: SQLite в памяти через `aiosqlite` с патчем `compiles(BigInteger, "sqlite")` → `INTEGER`. Полная схема Postgres проверяется отдельно (`alembic upgrade head` в CI на сервисе postgres). Подмена `get_db` и `get_redis_dep` через `app.dependency_overrides`.
- Целевое покрытие ≥ 60% (NFR-MNT-01), фактическое — 72.74%.

## 12. Что отложено в следующие фазы

| Решение | Фаза |
|---|---|
| Диалоговая логика бота, согласие № 152-ФЗ | Phase 2 |
| RuBERT, BERTopic, Celery-задачи | Phase 3 |
| PDF/XLSX отчёты, React SPA | Phase 4 |
| FR-AUTH-06 SMTP-реализация, FR-DB-07 безвозвратное удаление, NFR-REL-03 резервы, нагрузочное тестирование | Phase 5 |
