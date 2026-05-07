# CustDevAI — архитектурные решения

Этот документ фиксирует ключевые архитектурные решения, принятые на Phase 1 (Foundation), Phase 2 (Telegram bot) и Phase 3 (ML modules), и обоснования за ними. Обновляется по мере развития системы.

## Phase 3 — решения по ML-модулям

- **Стек ML фиксирован проектным решением** (см. §1.4.3–1.4.5 теор. главы): DeepPavlov/rubert-base-cased для sentiment (макро-F1 0.6–0.7 на RuSentNE-2023), BERTopic 0.16+ с эмбеддером intfloat/multilingual-e5-base, UMAP n_components=5/n_neighbors=15/cosine + HDBSCAN min_cluster_size=max(2, N/20)/euclidean, c-TF-IDF для 5–10 ключевых слов на тему. Не пересматривается.
- **Все ML-операции локально** (FR-SENT-08, NFR-SEC-09): никаких внешних API. Это конкурентное преимущество относительно Strella / Outset AI / Listen Labs (см. §2.4.2 аналитической главы).
- **Абстрактные интерфейсы** `SentimentAnalyzer` и `TopicModeler` в `apps/ml/base.py` (NFR-MNT-03). Конкретные реализации `RuBERTSentimentAnalyzer` и `BERTopicModeler` подключаются через `set_analyzers(analyzer_factory, modeler_factory)` в Celery-таске. В тестах `FakeSentimentAnalyzer` / `FakeTopicModeler` подменяют их без загрузки 1.5 ГБ весов.
- **Воспроизводимость** (FR-SENT-04, FR-TOP-07, NFR-COR-01): `set_global_seeds(42)` фиксирует random, numpy.random, torch CPU+CUDA, PYTHONHASHSEED. `torch.use_deterministic_algorithms(warn_only=True)` для cuDNN. UMAP/HDBSCAN получают `random_state=42`. Все seed-значения логируются в `ml_pipeline_start` structured-event.
- **Идемпотентность повторного запуска** (FR-RPT-07): `SentimentResultRepository.replace_for_campaign()` и `TopicResultRepository.replace_for_campaign()` делают DELETE+INSERT в одной транзакции. Дублей не накапливается. ON DELETE CASCADE на `topics → session_topics` из Phase 1 чистит связки автоматически.
- **Atomic status-lock** на `campaigns.analysis_status`: единый UPDATE с условием `IN (pending, completed, failed)` отсекает двойной запуск двух конкурирующих Celery-тасок (rowcount=0 → skip). Защита от race-condition без распределённых блокировок.
- **Celery-задача `analyze_campaign`**: `autoretry_for=(Exception,)`, `retry_backoff=True`, `retry_backoff_max=300`, `retry_jitter=True`, `max_retries=3`. На исчерпании ретраев — `mark_failed(error[:1024])`. Аналитик повторяет вручную через `POST /api/v1/campaigns/{id}/analyze`.
- **FR-SENT-06 (только русский)**: эвристика по доле кириллических букв с порогом 0.5. Не-русские ответы помечаются `is_language_error=True` и пропускаются репозиторием при INSERT — не загрязняют статистику.
- **FR-TOP-03 (top-3 цитаты)**: cosine-distance от centroid эмбеддингов кластера, sparse-схема хранения: для top-3 ассоциаций `session_topics.representative_quote = текст ответа`, для остальных — NULL. Без новой колонки `distance_to_centroid`.
- **FR-TOP-04 (target_topic_count)**: `campaigns.target_topic_count SMALLINT NOT NULL DEFAULT 10 CHECK BETWEEN 3 AND 20` через миграцию 0003. Настраивается через `PATCH /api/v1/campaigns/{id}`. Переживает re-run.
- **FR-BOT-09 закрытие — двухэтапный push**: первый «все сессии завершены, ML-анализ запущен» из Phase 2 + второй «ML-анализ завершён» из Phase 3 (`notify_researcher_analysis_ready`). Текст с количествами тем и ответов, без URL до Phase 4.
- **Trigger автоматического запуска**: после первого push `notify_service.maybe_notify_researcher_all_completed()` шлёт `analyze_campaign.delay(campaign_id)`. При недоступности Celery-брокера ошибка enqueue логируется но не фатальна — аналитик запустит вручную.

---

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
