# Disaster Recovery — CustDevAI

Закрывает приёмочные критерии **NFR-REL-03** (резервное копирование),
**NFR-REL-05** (RTO ≤ 60 минут) и **NFR-REL-06** (RPO ≤ 24 часа), а также
функциональное требование **FR-DB-08**.

## 1. Стратегия резервного копирования

| Параметр | Значение | Источник |
|---|---|---|
| Периодичность | 1 раз в сутки (03:00 UTC) | NFR-REL-03 |
| Глубина | последние 7 копий | FR-DB-08 |
| Формат | `pg_dump -Fc` (custom format, поддерживает `pg_restore -j`) | apps/worker/tasks/backup.py |
| Хранилище | `BACKUP_STORAGE_DIR` (default `/var/lib/custdevai/backups`); том `backups_storage` в docker-compose | docker-compose.yml |
| Целостность | каждая копия сопровождается SHA-256 хешем в логе | `_sha256_of_file()` |
| Ротация | старые копии удаляются после успешной записи новой | `_rotate(keep=BACKUP_RETENTION_COUNT)` |
| RPO | ≤ 24 часа (по факту расписания) | NFR-REL-06 |
| RTO | ≤ 60 минут (тестовое восстановление) | NFR-REL-05 |

Расписание Celery beat задано в `apps/worker/celery_app.py`:

```python
"backup-database-daily": {
    "task": "backup.database",
    "schedule": crontab(hour=3, minute=0),
},
```

При сбое `pg_dump` Celery повторяет 2 раза с задержкой 5 минут. После
исчерпания retry — таск падает, отсутствие свежей копии видно в логе и
мониторинге.

## 2. Ручной триггер копии

Используется для проверки работоспособности и перед запланированной
миграцией (например, перед `alembic upgrade head`).

```bash
docker compose exec worker celery -A apps.worker.celery_app call backup.database
docker compose exec worker ls -lh /var/lib/custdevai/backups
```

Файл получает имя `custdevai-YYYYMMDD-HHMMSS.dump` (UTC).

## 3. Процедура восстановления (RTO ≤ 60 минут)

Полное восстановление БД из последней копии. **Производится на чистом
PostgreSQL-инстансе** (повторное накатывание поверх существующей БД
требует флага `--clean --if-exists`, см. шаг 4).

### Шаг 1 — Остановить зависимые сервисы

Чтобы не дать активным транзакциям записать данные мимо восстанавливаемой
БД, останавливаем API, бот, worker:

```bash
docker compose stop api bot worker worker-beat
```

PostgreSQL и Redis оставляем running.

### Шаг 2 — Выбрать копию для восстановления

```bash
docker compose exec worker ls -lt /var/lib/custdevai/backups | head -10
```

По умолчанию — самая свежая (`*-HHMMSS.dump`). При повреждении свежей
можно откатиться на любую из 7 копий (RPO = 24 ч × выбранная давность).

### Шаг 3 — (Опционально) Сохранить текущее состояние

Если текущая БД содержит хотя бы частично актуальные данные, **до**
восстановления делаем дополнительный backup, не входящий в ротацию:

```bash
TS=$(date -u +%Y%m%d-%H%M%S)
docker compose exec worker pg_dump -Fc \
    "$DATABASE_URL_LIBPQ" \
    -f /var/lib/custdevai/backups/pre-restore-$TS.dump
```

### Шаг 4 — Восстановление

`pg_restore -Fc` с `--clean --if-exists` удаляет старые объекты перед
вставкой. На пустой БД флаги безопасны.

```bash
BACKUP=/var/lib/custdevai/backups/custdevai-20260530-030000.dump

docker compose exec postgres \
    pg_restore \
    --clean --if-exists \
    --no-owner --no-privileges \
    -j 4 \
    --dbname "${DATABASE_URL_LIBPQ}" \
    "$BACKUP"
```

`-j 4` — параллельное восстановление в 4 потока (на 4-vCPU тире
Selectel — оптимально). На больших БД даёт x2–x3 ускорения.

### Шаг 5 — Применить миграции

После восстановления убедиться, что схема соответствует HEAD-ревизии:

```bash
docker compose start api
docker compose exec api alembic current
docker compose exec api alembic upgrade head
```

Если backup сделан до 0005 миграции, `upgrade head` доедет до 0005
(pg_trgm GIN индекс).

### Шаг 6 — Перезапуск зависимых сервисов

```bash
docker compose start bot worker worker-beat
```

### Шаг 7 — Smoke-тест

```bash
curl -fsS https://<custdevai-domain>/health
# Авторизация в SPA + GET /api/v1/users/me
# Запуск интервью через бота (один цикл /start → consent → answer → finish)
```

Если все smoke-проверки прошли — RTO зафиксирован.

## 4. Замер RTO на тестовом стенде

Перед защитой ВКР RTO должен быть измерен фактически и зафиксирован в
этом документе. Процедура:

1. На production-инстансе Selectel создать тестовую копию через
   `celery call backup.database`.
2. На отдельном чистом инстансе Selectel (минимальный тариф) развернуть
   стек `docker compose up -d postgres`.
3. Скопировать `custdevai-*.dump` на тестовый инстанс.
4. Засечь время от запуска `pg_restore` до успешного `curl /health`.
5. Записать значение в таблицу ниже.

### Фактические замеры

| Дата | Backup-размер | Кол-во таблиц | Длительность | RTO_target | Статус |
|---|---|---|---|---|---|
| _TBD_ | _TBD_ | 16 | _TBD_ | ≤ 60 мин | _TBD_ |

## 5. RPO ≤ 24 часа (NFR-REL-06)

RPO обеспечивается расписанием Celery beat: один pg_dump в сутки в 03:00 UTC.
При потере данных между бэкапами максимально возможная потеря — 24 часа.

В случае увеличения нагрузки и необходимости снизить RPO до 1 часа —
переходим на WAL-archiving + точечное восстановление (PITR). Это Phase 6
(не требуется для приёмки ВКР).

## 6. Что не входит в DR-стратегию

- **WAL-archiving / PITR** — Phase 6.
- **Геораспределённые копии** (например, S3 в другом регионе Selectel) —
  Phase 6.
- **Автоматический failover** на резервный инстанс — не требуется
  для приёмки (NFR-REL-01 = 99% uptime, что допускает до 14 минут
  простоя в сутки).
- **Восстановление S3-объектов отчётов** — в Phase 5 хранилище
  локальное (LocalFileSystemBackend); том `reports_storage` копируется
  отдельной procedure `docker volume backup`.

## 7. Проверка соответствия требованиям

| Требование | Реализация | Доказательство |
|---|---|---|
| FR-DB-08 — ежедневное резервное копирование, 7 копий | `apps/worker/tasks/backup.py` + Celery beat 03:00 UTC | `tests/unit/test_backup_rotation.py` (8 проходов) |
| NFR-REL-03 — full backup ≥ 1/сутки | Celery beat schedule | docker-compose `worker-beat` |
| NFR-REL-05 — RTO ≤ 60 минут | Процедура §3, замер §4 | `docs/DISASTER_RECOVERY.md` |
| NFR-REL-06 — RPO ≤ 24 часа | расписание 03:00 UTC | celery_app.py beat_schedule |
