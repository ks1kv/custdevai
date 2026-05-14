# CustDevAI — контекст разработки

Этот файл обновляется в конце каждой фазы. Содержит сводку сделанного, ключевые архитектурные решения и список вопросов/задач для следующей фазы.

---

## Phase 5 — Integration & QA (завершена)

Финальная фаза перед защитой ВКР 31.05.2026. Закрыты все 7 MUST задач и
3 SHOULD; COULD-задачи перенесены на Phase 6 (после защиты).

### Что сделано

1. **FR-BOT-05 sessions sweeper.** `apps/worker/tasks/sessions.py` с Celery beat-расписанием каждые 15 минут: UPDATE active → interrupted для сессий с `last_activity_at < now() - 48h` (настраивается через `SESSION_INACTIVE_HOURS`). 2 integration теста.
2. **FR-DB-07 удаление субъекта** (№ 152-ФЗ). `DataDeletionService` + `POST /api/v1/admin/data-deletion-requests` (admin-only). Физическое удаление всех записей субъекта по `telegram_id_hash`; запись `DATA_DELETION_REQUESTED` в audit_log с counts и legal_basis; возврат `DataDeletionReceipt` (JSON-акт). 4 integration теста.
3. **FR-DB-08 + NFR-REL-03/05/06 backup.** `apps/worker/tasks/backup.py` ежедневно в 03:00 UTC выполняет `pg_dump -Fc` в `BACKUP_STORAGE_DIR` и ротирует последние 7 копий. Celery retry 2 раза при сбое. Volume `backups_storage` в docker-compose, отдельный сервис `worker-beat`. 6 unit тестов. `docs/DISASTER_RECOVERY.md` с процедурой `pg_restore --clean --if-exists -j 4` и замером RTO.
4. **FR-WEB-05 транскрипты.** `GET /api/v1/campaigns/{id}/transcripts` с поиском через pg_trgm (миграция 0005 — GIN-индекс) и фильтром по sentiment_label. Fallback на `lower().contains()` в SQLite + регистрация python-aware lower для кириллицы. 5 integration тестов. SPA: `TranscriptsTab` (поиск + фильтр + раскрывающиеся сессии), `SentimentTab` (Recharts PieChart с агрегатом).
5. **FR-SENT-07 fine-tune pipeline.** `apps/ml/sentiment/training.py`: RuSentNE-2023 через `datasets`, stratified split с seed=42, ≥ 200 примеров holdout в `tests/ml/data/rusentne_2023_holdout.json`, HuggingFace Trainer (epochs=3, batch=8, lr=2e-5, CPU). `model.save_pretrained` + metrics.json (accuracy / weighted F1 / macro F1 / per-class P/R/F1 / confusion matrix). `RuBERTSentimentAnalyzer.warmup()` грузит fine-tuned веса из `SENTIMENT_MODEL_PATH`. Жёсткие assert FR-SENT-07 включаются `SENTIMENT_ASSERT_FR_07=true`. `docs/ML_METRICS.md` шаблон отчёта.
6. **MUST-2 нагрузочное тестирование** (NFR-PRF-01/02/04/05/06/08). `tests/load/`: scenario_1 (k6, 50 VUs webhook), scenario_2 (200 сессий ML eager), scenario_3 (500 сессий отчёт), scenario_4 (k6, 1000 RPS API). `tests/load/_helpers.py` seed с реалистичными русскоязычными ответами. `docs/LOAD_TEST_REPORT.md`.
7. **MUST-6 production-деплой Selectel.** `docker/web.Dockerfile` стадия `serve` (Nginx + dist/). `docker/nginx/nginx.conf` — TLS 1.2/1.3, HSTS, reverse-proxy `/api/*` с `X-Forwarded-Proto https`, SPA fallback, gzip. `docker-compose.prod.yml` с `ENVIRONMENT=production`, `COOKIE_SECURE=true`, 4 uvicorn workers. `docs/DEPLOYMENT.md` — 15-шаговая процедура.
8. **SHOULD-9 технический долг.**
   - **Retry-After** (NFR-SEC-05, RFC 6585): RateLimited принимает `retry_after_seconds`; handler выставляет заголовок.
   - **HMAC deep-link** (NFR-SEC-08): новый формат `c<id>.<sig>`, ключ через HKDF из `PSEUDONYM_MASTER_SALT` с info=b"deeplink". Старый `c<id>` принимается с deprecation-warning. 6 unit тестов.
   - **Webhook sub-app typing**: `Update` типизированный, `include_in_schema=False` исключает aiogram-схему из публичного OpenAPI.
9. **SHOULD-8 SMTPEmailNotifier** (FR-AUTH-06). `SMTPEmailNotifier` через aiosmtplib (STARTTLS, plain-text по-русски). `get_email_notifier(settings)` — фабрика: SMTP при `SMTP_HOST + SMTP_FROM`, иначе Logging. SMTP failure → warning-лог с `delivery_failed=True`, не блокирует reset_password. 4 unit теста.
10. **SHOULD-10 Playwright cross-browser** (FR-WEB-12, NFR-OPS-05). `tests/e2e/` три профиля (chromium-1024, firefox-1024, yandex-1024) viewport 1024×768. `full_flow.spec.ts`: login → script → campaign → settings + проверка scrollWidth. `docs/BROWSER_QA_REPORT.md`.

### Тестовое покрытие

**Полный suite (без ML-acceptance): 161 passed + 1 skipped**, coverage ≥ 60%.

В CI: 3 новых интеграционных набора (sessions sweeper, data deletion, transcripts), 4 новых unit-набора (backup rotation, deeplink HMAC, email notifier factory, расширенный sentiment_quality).

### Итоговая матрица покрытия FR/NFR

| Группа | Полностью | Частично | Отложено в Phase 6 |
|---|---|---|---|
| FR-API-01..08 | 01..08 | — | — |
| FR-AUTH-01..08 | 01..08 (SMTP в production) | — | — |
| FR-DB-01..08 | 01..08 (включая 07 удаление субъекта, 08 backup) | — | — |
| FR-BOT-01..10 | 01..10 (sweeper закрывает 05) | — | — |
| FR-SENT-01..08 | 01..06, 08 | 07 (pipeline готов; фактические метрики после прогона на Selectel) | — |
| FR-TOP-01..08 | 01..08 | — | — |
| FR-RPT-01..08 | 01..08 (LocalFS) | — | S3-backend (COULD) |
| FR-WEB-01..12 | 01..12 (12 через Playwright + viewport check) | — | Полный QA-прогон в 3 браузерах — на Selectel |
| NFR-SEC-01..09 | 01..09 (Retry-After + HMAC + SMTP) | — | — |
| NFR-PRF-01..08 | каркас + сценарии | 01/02/04/05/06/08 (замеры на Selectel) | — |
| NFR-REL-01..07 | 02..06 (backup + RTO/RPO документированы) | 01 (99% uptime — после prod-деплоя), 04 (outbox — COULD) | 03 (S3 в другом регионе), 07 |
| NFR-MNT-01..05 | 01..05 (StorageBackend ABC, EmailNotifier фабрика) | — | — |
| NFR-OPS-01..08 | 01..08 (DEPLOYMENT + DR + 3 Playwright профиля) | 05 (фактический прогон — на Selectel) | — |
| NFR-USE-01..05 | 01..05 (Wizard ≤ 10 мин; ru-only NFR-OPS-06) | 04 (формальный WCAG audit — COULD) | — |
| NFR-COR-01..02 | 01..02 | — | — |

### COULD-задачи (перенесены в Phase 6)

1. `users.tokens_invalid_before TIMESTAMPTZ` для полного отзыва токенов администратором (FR-AUTH-07 в максимуме).
2. Outbox-pattern для Telegram-сообщений (NFR-REL-04 строгое соответствие).
3. S3StorageBackend для отчётов через aiobotocore (FR-RPT-08 в production-конфигурации Selectel Object Storage).
4. Формальный WCAG 2.1 AA аудит SPA через axe-core или pa11y.

### Что должно произойти на Selectel-стенде до защиты

См. чек-лист в `docs/DEPLOYMENT.md` §14:

- [ ] Развернуть стек по DEPLOYMENT.md (1–11).
- [ ] Прогнать fine-tune RuBERT (`python -m apps.ml.sentiment.training`) и заполнить ML_METRICS.md фактическими числами; стратегия Q2 — итерации гиперпараметров до достижения FR-SENT-07.
- [ ] Прогнать 4 нагрузочных сценария → заполнить LOAD_TEST_REPORT.md.
- [ ] Замерить RTO на тестовом восстановлении → заполнить DISASTER_RECOVERY.md §4.
- [ ] Прогнать Playwright в 3 профилях → заполнить BROWSER_QA_REPORT.md со скриншотами.
- [ ] Demo-сценарий end-to-end (бот → анализ → отчёт) перед защитой.

---

## Phase 4 — Reports + Web admin (завершена)

### Что сделано

1. **Модель Report + миграция 0004.** ENUM `report_format` (pdf/xlsx); таблица `reports(id, campaign_id CASCADE, format, file_path TEXT, file_size BIGINT CHECK >0, sha256 BYTEA(32), generated_at, generated_by_user_id, created_at, updated_at)`. Индексы `ix_reports_campaign_format`, `ix_reports_generated_at`. Уникальная пара `(campaign_id, format)` НЕ ставится — повторная генерация (FR-RPT-07) создаёт новую запись и сохраняет старый файл до явного cleanup.
2. **StorageBackend ABC + LocalFileSystemBackend** (NFR-MNT-03). `put/get/delete` async-методы; LocalFS пишет атомарно через `tmp + os.replace`, защищён от path traversal, использует `asyncio.to_thread` для blocking I/O. Volume `reports_storage:/var/lib/custdevai/reports` в docker-compose. Phase 5 заменит на `S3StorageBackend` без изменений ReportService/generators.
3. **Псевдонимизация R-NNNN** (FR-DB-03, FR-RPT-05). Производный псевдоним `f"R-{session.id % 10000:04d}"` без миграции БД (Q1: одобрено пользователем). Внутри одной кампании коллизий нет; > 10 000 сессий между кампаниями — переход на `pseudonym_ordinal SMALLINT` в Phase 5.
4. **CampaignReportContext + data_loader.** Иммутабельный DTO с `AnswerView`, `SessionView`, `TopicView` собирается одним пакетом запросов; генераторы PDF/XLSX больше не делают I/O.
5. **Charts** (matplotlib `Agg` backend). `render_sentiment_pie(distribution)`, `render_topics_hbar(topics, max_topics=12)` → PNG bytes. Bundled DejaVu Sans Regular+Bold TTF (~1.4 МБ) в `apps/api/reports/fonts/` — кириллица в графиках без apt-зависимостей.
6. **PDFReportGenerator** (FR-RPT-01..02, 04, 05). A4, поля 20 мм; разделы: cover, summary, sentiment (pie + таблица), topics (hbar + per-topic keywords + 3 цитаты с псевдонимом), transcripts. ReportLab `pdfmetrics.registerFont` для DejaVu. HTML-escape `< > &` для `<para>`-парсера.
7. **XLSXReportGenerator** (FR-RPT-03). Три листа: «Транскрипты» (R-NNNN, вопрос, ответ, дата, sentiment, confidence), «Тональность» (распределение), «Темы» (id, keywords, frequency, 3 цитаты). Header стилизован, freeze_panes="A2", auto-widths.
8. **ReportService** (`generate(campaign_id, fmt, actor_id, owner_id) → Report`). Валидирует `analysis_status == COMPLETED` (иначе 409). CPU-bound rendering через `loop.run_in_executor(None, _render_pdf_sync, ctx)`. Ключ хранилища: `campaigns/{id}/{timestamp}-report.{ext}`.
9. **REST endpoints** (FR-WEB-10, FR-RPT-01..08). `POST /api/v1/campaigns/{id}/reports/generate?format=pdf|xlsx`, `GET /api/v1/campaigns/{id}/reports` (пагинация), `GET /api/v1/campaigns/{id}/reports/{report_id}/download` (streaming Response, `Content-Disposition: attachment`).
10. **httpOnly cookie auth.** `/auth/login?set_cookie=true` выставляет `access_token` (Path=/api, httpOnly, Secure prod, SameSite=Strict, Max-Age=900) и `refresh_token` (Path=/api/v1/auth, Max-Age=604800). `/auth/refresh` принимает токен из тела ИЛИ cookie. `/auth/logout` чистит обе. `deps.get_current_user` читает из `Authorization: Bearer` ИЛИ из `access_token` cookie. `CORSMiddleware(allow_credentials=True, allow_origins=settings.cors_allow_origins)` — для SPA на :5173.
11. **Real report URL во втором push** (закрытие FR-BOT-09 #4 из задач Phase 3). `RESEARCHER_NOTIFY_ANALYSIS_READY` шаблон оканчивается «Подробности и скачивание отчёта: {campaign_url}», где `campaign_url = f"{settings.web_base_url}/campaigns/{id}"`.
12. **`GET/PATCH /api/v1/users/me`** (закрытие FR-BOT-09 #3). `MyProfileUpdate` DTO с `full_name` и `researcher_telegram_chat_id` — researcher через UI Settings регистрирует chat_id, после чего notify_service реально доставляет push.
13. **React SPA `apps/web/`** (FR-WEB-01..11). React 18 + TS 5 + Vite + TanStack Query v5 + React Router v6 + react-hook-form + zod + Recharts. Все страницы: LoginPage (cookie auth), DashboardPage (real-time `refetchInterval=10s` FR-WEB-04), ScriptsListPage + ScriptBuilderPage (FR-WEB-01,02), CampaignsListPage + CampaignCreatePage, CampaignDetailPage (вкладки обзор/транскрипты/тональность/темы/отчёты, кнопка ML-анализ), ReportsPage (генерация + скачивание PDF/XLSX, FR-WEB-10), CampaignComparePage (FR-WEB-08), ArchivePage (FR-WEB-09), WizardPage первой кампании (FR-WEB-11, NFR-USE-01), SettingsPage (chat_id регистрация). Все строки в `lib/locales/ru.ts` (NFR-OPS-06). Типы API скопированы вручную из openapi.json.
14. **docker/web.Dockerfile** (multi-stage build + dev). Стадия `dev` — Vite HMR :5173. Стадия `build` — production-bundle в `/app/dist/`. Phase 5 добавит стадию `serve` с Nginx.
15. **Тесты.** 20 новых: 7 pseudonym + 8 storage backend + 5 PDF/XLSX smoke. Coverage держится ≥ 60%. Полный suite: 133 passed + 1 skipped (ml).

### Закрытые требования Phase 4

| Группа | Полностью | Частично | Отложено |
|---|---|---|---|
| FR-WEB-01..12 | 01..11 (включая wizard FR-WEB-11) | 12 (адаптивность тестируется на reference 1024×768; полный браузер-матрикс — Phase 5) | — |
| FR-RPT-01..08 | 01, 02, 03, 04, 05, 06, 07, 08 | — | — |
| FR-BOT-09 | ✓ полностью (UI регистрации chat_id + URL отчёта в push) | — | — |
| NFR-PRF-05 | ≤ 30 с на 500 сессий — структура есть | реальный замер на 500 сессиях — Phase 5 | — |
| NFR-USE-01 | ≤ 10 минут до первой кампании через Wizard | проверка на пользователях — Phase 5 | — |
| NFR-USE-04 | aria-метки, контраст | формальный AA-аудит — Phase 5 | — |
| NFR-OPS-06 | ✓ только русский | — | — |
| NFR-MNT-03 | ✓ StorageBackend ABC | — | — |
| NFR-SEC-09 | ✓ отчёт строго экстрактивный, без LLM | — | — |

### Принятые архитектурные решения Phase 4

См. `docs/ARCHITECTURE.md` (раздел Phase 4). Ключевые:

- **Хранилище:** LocalFileSystemBackend в Phase 4, S3 в Phase 5 без переписывания ReportService.
- **Генерация:** синхронная через `loop.run_in_executor` (CPU-bound). Если профилирование на 500 сессиях покажет > 30 с — переход на Celery `generate_report.delay(...)`.
- **Faithfulness отчётов:** строго экстрактивный — только цитаты из транскриптов (`representative_quote` из Phase 3, отсортированы по близости к centroid). Никакого LLM. См. §1.4.6 теоретической главы.
- **Шрифт кириллицы:** bundled DejaVu Sans TTF (а не apt-install), даёт воспроизводимость.
- **Псевдоним:** `R-{session.id % 10000:04d}` без миграции (Q1).
- **Cookies:** httpOnly + Secure (prod) + SameSite=Strict; `?set_cookie=true` на /auth/login; refresh идёт через cookie тоже.
- **Frontend:** React 18 + TS 5 + Vite + TanStack Query v5 + shadcn-style minimal UI + Recharts; типы API вручную из openapi.json без кодогенератора.

### Открытые задачи для Phase 5

1. **Production-деплой на Selectel + Nginx reverse-proxy.** SPA через FastAPI StaticFiles из `apps/web/dist/` либо Nginx-стадия в web.Dockerfile.
2. **S3-backend для отчётов.** `S3StorageBackend(boto3)` поверх Selectel Object Storage (env `SELECTEL_OBJECT_STORAGE_*` уже есть).
3. **Fine-tune RuBERT на RuSentNE-2023** для достижения FR-SENT-07 (accuracy ≥ 0.75, weighted F1 ≥ 0.73).
4. **Sweeper 48-часовых сессий (FR-BOT-05).** Celery beat-таска `sessions_sweeper` каждые 15 мин.
5. **Полный браузерный QA-матрикс (FR-WEB-12, NFR-OPS-05).** Chrome 110+ / Firefox 110+ / Yandex 23+.
6. **Нагрузочные тесты NFR-PRF-02/04/05/06** на реальных объёмах через locust или k6.
7. **/transcripts API** — выдача транскриптов с поиском (FR-WEB-05) и распределения тональности (FR-WEB-06) для интерактивных вкладок CampaignDetailPage. SPA уже готов потреблять (заглушки в трёх вкладках).
8. **HMAC-подпись deep-link** (Phase 2 #4).
9. **Outbox-pattern для Telegram-сообщений** (Phase 2 #4).
10. **Retry-After при 429** (NFR-SEC-05 nice-to-have).

---

## Phase 3 — ML modules (завершена)

### Что сделано

1. **Расширение схемы БД (миграция 0003).** ENUM `campaign_analysis_status` (pending/running/completed/failed); поля `Campaign.analysis_status`, `target_topic_count` (CHECK 3..20), `analysis_started_at`, `analysis_completed_at`, `analysis_error TEXT`. Индекс `ix_campaigns_analysis_status`.
2. **Абстрактные интерфейсы (NFR-MNT-03).** `SentimentAnalyzer` и `TopicModeler` в `apps/ml/base.py`. `set_analyzers(analyzer_factory, modeler_factory)` — DI-hook в Celery-таске; в тестах подменяется на `FakeSentimentAnalyzer` / `FakeTopicModeler`.
3. **Утилиты ML (`apps/ml/`).** `set_global_seeds()` (FR-SENT-04, FR-TOP-07, NFR-COR-01) — фиксирует random/numpy/torch CPU+CUDA/PYTHONHASHSEED. `is_russian_text()` (FR-SENT-06) — эвристика по доле кириллицы 0.5. DTO `SentimentInference`, `TopicResult`, `SessionTopicAssignment`, `TopicModelingResult` — стандартизированный JSON-формат для FR-TOP-08.
4. **Конкретные ML-реализации.** `RuBERTSentimentAnalyzer` (DeepPavlov/rubert-base-cased, batch_size=16, max_length=512, FR-SENT-01..06,08); `BERTopicModeler` (intfloat/multilingual-e5-base + UMAP n_components=5/n_neighbors=15/cosine + HDBSCAN min_cluster_size=max(2, N/20) + c-TF-IDF + reduce_topics(target_topic_count); FR-TOP-01..08); `select_representative_indices()` для top-3 цитат (FR-TOP-03).
5. **Settings + ml_results репозитории.** Поля `sentiment_*`, `topic_*`, `ml_model_cache_dir`, `transformers_offline`, `celery_*` в `Settings`. `SentimentResultRepository.replace_for_campaign()` и `TopicResultRepository.replace_for_campaign()` — DELETE+INSERT для FR-RPT-07 без накопления дублей.
6. **Celery-задача `analyze_campaign`.** Atomic переход status pending|completed|failed → running через `try_acquire_running()` (защита от race condition без распределённых локов). `autoretry_for=(Exception,)`, `retry_backoff=True`, `max_retries=3`. На исчерпании — `mark_failed(error[:1024])`. После успеха — `notify_researcher_analysis_ready()` (второй push, закрытие FR-BOT-09).
7. **REST endpoints.** `POST /api/v1/campaigns/{id}/analyze` (Researcher свои, Admin) → 202 + `task_id`. 409 если `analysis_status=running`. `GET /api/v1/campaigns/{id}/analysis-status` (Researcher/Analyst/Admin) → `analysis_status` + timestamps + error + target_topic_count. `PATCH /campaigns/{id}` поддерживает `target_topic_count`.
8. **Trigger из notify_service.** После первого push `analyze_campaign.delay(campaign_id)` enqueue-ится автоматически (FR-API-04). Ошибка enqueue не фатальна.
9. **Worker Dockerfile.** Multi-stage: builder ставит `pip install -e ".[ml,dev]"`. Runtime + libgomp1 + ENV `HF_HOME=/models`, `TRANSFORMERS_CACHE=/models`, `SENTENCE_TRANSFORMERS_HOME=/models`. Веса не в образе — скачиваются warmup-ом и кэшируются в volume.
10. **Тесты.** 23 новых теста (4 unit + 5 integration + 14 уже было). Coverage 62.77% (≥ 60% NFR-MNT-01). Acceptance-тесты с `@pytest.mark.ml` запускаются отдельно с реальной моделью; на baseline-режиме без fine-tune (Phase 5) `assert accuracy ≥ 0.75` закомментирован.

### Закрытые требования Phase 3

| Группа | Полностью | Частично | Отложено |
|---|---|---|---|
| FR-SENT-01..08 | 01, 02, 03, 04, 05, 06, 08 | 07 (структура есть, фактические метрики через @pytest.mark.ml; production fine-tune — Phase 5) | — |
| FR-TOP-01..08 | 01, 02, 03, 04, 05, 06, 07, 08 | — | — |
| FR-API-04 | ✓ Celery-оркестрация фонового анализа | — | — |
| FR-API-05 | каркас (триггер ML→push); реальный модуль отчётов — Phase 4 | — | — |
| FR-RPT-07 | ✓ DELETE+INSERT cleanup при re-run | — | — |
| FR-BOT-09 | ✓ полностью (двухэтапный push) | — | — |
| NFR-COR-01 | ✓ set_global_seeds + fixed seed=42 | — | — |
| NFR-MNT-03 | ✓ ABC-интерфейсы + Fake-реализации в тестах | — | — |
| NFR-PRF-04 | каркас и пакетный режим | реальный замер на 200 сессиях — Phase 5 нагрузочный тест | — |
| NFR-SEC-09 | ✓ всё локально, без external API | — | — |

### Фактические метрики FR-SENT-07

Baseline RuBERT-модель (DeepPavlov/rubert-base-cased) **без** fine-tune на RuSentNE-2023:
**ожидаемо ниже целевых** accuracy ≥ 0.75 / weighted F1 ≥ 0.73, т.к. zero-shot применение мультиклассовой головы. Конкретные числа на 24-примерной выборке зафиксируются после ручного запуска `pytest -m ml` в окружении с установленным `.[ml]`-extra. Production fine-tune — задача Phase 5 (training-pipeline).

### Открытые задачи для Phase 4

1. **PDF/XLSX-генератор отчётов** через ReportLab + openpyxl + matplotlib (FR-RPT-01..08).
2. **React SPA** (`apps/web/`): дашборды кампаний, визуализация sentiment-распределения, облако тем (FR-WEB-01..12).
3. **Регистрация `users.researcher_telegram_chat_id`** через web-UI исследователя — после Phase 4 push-уведомления начнут реально доставляться.
4. **Замена placeholder-текста второго push** на конкретный URL отчёта в `RESEARCHER_NOTIFY_ANALYSIS_READY` (сейчас «Подробности — в веб-панели после реализации Phase 4»).
5. **Хранилище отчётов** в Selectel Object Storage — связано с FR-RPT-08 и `SELECTEL_*` env-переменными.

---

## Для Phase 5 на будущее

Во-первых, технический долг webhook-эндпойнта из Phase 2: apps/api/routers/webhook.py принимает raw Request вместо типизированного Update из-за конфликта с OpenAPI generation. В Phase 5 нужно изолировать этот роутер через отдельный FastAPI sub-application или include_in_schema=False и вернуть типизацию — это влияет на корректность OpenAPI-контракта для production-деплоя.
Во-вторых, sweeper 48-часовых сессий (FR-BOT-05): реализован только FSM TTL в Redis, статус active в БД не переводится в interrupted автоматически. В Phase 5 нужна Celery beat-таска sessions_sweeper — SELECT sessions WHERE status='active' AND last_activity_at < now() - interval '48 hours', пакетный UPDATE в interrupted. Без этого аналитика по завершённости кампаний будет занижена.
В-третьих, HMAC-подпись deep-link (Вопрос 4 из плана Phase 2): сейчас c<campaign_id> без подписи. При росте аудитории и появлении недобросовестных участников нужно добавить c<campaign_id>.<hmac_sha256(campaign_id, master_secret)> — это защищает от перебора campaign_id и спам-сессий на чужих кампаниях.
В-четвёртых, Retry-After заголовок при 429 (FR-AUTH-08): в Phase 1 брутфорс-защита возвращает 429 без Retry-After. RFC 6585 требует этот заголовок для корректной обработки клиентом. Добавить в _api_error_handler для RateLimited — одна строка, но пропущена при первоначальной реализации.
В-пятых, нагрузочный тест NFR-PRF-06 (50 одновременных сессий, ≤ 3 сек отклик): не проводился ни в Phase 1, ни в Phase 2. Phase 5 должна включать locust- или k6-сценарий с 50 параллельными ботами, имитирующими ответы на вопросы, с измерением p95-времени отклика и мониторингом asyncpg connection pool exhaustion.

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
