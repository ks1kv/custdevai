# Production-деплой CustDevAI на Selectel

Пошаговая процедура развёртывания на чистом Selectel-инстансе. Закрывает
**MUST-6 Phase 5**.

## 0. Что должно быть у тебя до старта

| Артефакт | Откуда |
|---|---|
| Selectel-аккаунт + биллинг | https://my.selectel.ru/ |
| SSH-ключ для root/admin доступа | пользователь |
| Публичный домен или *.selcloud.ru поддомен | пользователь |
| Telegram-бот токен | @BotFather (новый бот или прод-инстанс существующего) |
| Минимальный тариф | 4 vCPU / 8 GB RAM / 80 GB SSD (для ML-worker и pg_dump) |

## 1. Provisioning Selectel VPS

1. В Cloud-консоли создаём облачный сервер с Ubuntu 22.04 LTS.
2. Базовые ресурсы: 4 vCPU, 8 GB RAM, 80 GB NVMe SSD. Регион — Москва или Санкт-Петербург (низкая латентность к Telegram API).
3. Открываем входящие порты: 22 (SSH), 80 (HTTP для ACME), 443 (HTTPS).
4. Закрываем 5432, 6379, 8000 — они доступны только внутри docker-сети.

## 2. DNS

Создаём A-запись (если домен на cloudflare/reg.ru/Selectel DNS):

```
custdevai.example.com  →  <IP_адрес_инстанса>
```

TTL 300 для быстрых правок при первом запуске.

## 3. Подготовка хоста

```bash
# SSH вход.
ssh root@<IP>

# Обновляемся.
apt update && apt upgrade -y

# Создаём отдельного пользователя, не работаем под root.
adduser --disabled-password --gecos "" custdev
usermod -aG sudo custdev
mkdir -p /home/custdev/.ssh
cp /root/.ssh/authorized_keys /home/custdev/.ssh/
chown -R custdev:custdev /home/custdev/.ssh
chmod 700 /home/custdev/.ssh
chmod 600 /home/custdev/.ssh/authorized_keys

# Установка Docker.
apt install -y docker.io docker-compose-plugin
usermod -aG docker custdev

# certbot для Let's Encrypt.
apt install -y certbot

# Базовая защита.
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Опционально: fail2ban для SSH.
apt install -y fail2ban
systemctl enable --now fail2ban
```

С этого момента SSH-логин — под `custdev`.

## 4. Клонирование репозитория

```bash
ssh custdev@<IP>
cd ~
git clone https://github.com/ks1kv/custdevai.git
cd custdevai
git checkout main
```

## 5. Конфигурация `.env`

```bash
cp .env.example .env
nano .env
```

Заполняем обязательные:

```ini
ENVIRONMENT=production
PUBLIC_DOMAIN=custdevai.example.com

# Postgres (используем СИЛЬНЫЕ случайные значения).
POSTGRES_PASSWORD=$(openssl rand -base64 32)

# JWT и pseudonym salt — 64 hex символа.
JWT_SECRET=$(openssl rand -hex 32)
PSEUDONYM_MASTER_SALT=$(openssl rand -hex 32)

# Bcrypt cost factor (NFR-SEC-02).
BCRYPT_COST_FACTOR=12

# Telegram-бот (FR-BOT-*).
TELEGRAM_BOT_TOKEN=<из @BotFather>
TELEGRAM_WEBHOOK_URL=https://custdevai.example.com/api/v1/telegram/webhook
TELEGRAM_WEBHOOK_SECRET=$(openssl rand -hex 32)

# Web base URL (Phase 4: используется во втором push).
WEB_BASE_URL=https://custdevai.example.com
CORS_ALLOW_ORIGINS=["https://custdevai.example.com"]

# SMTP — если есть сторонний MTA (SHOULD-8); иначе оставить пустым.
SMTP_HOST=
SMTP_PORT=587
SMTP_FROM=noreply@custdevai.example.com
```

Все секреты — не коммитим (NFR-SEC-06; .gitignore уже исключает .env).

## 6. Let's Encrypt: выпуск сертификата

Phase-trick: для первого выпуска нужно HTTP-серверу слушать на 80,
но nginx-контейнер ещё не запущен. Используем standalone-режим certbot
до первого запуска docker-compose:

```bash
# 1. Поднимаем certbot в standalone — он сам становится сервером :80.
sudo certbot certonly --standalone \
    --agree-tos --non-interactive \
    --email admin@custdevai.example.com \
    -d custdevai.example.com

# 2. Создаём symlinks для docker монтирования.
mkdir -p docker/nginx/certs
sudo cp /etc/letsencrypt/live/custdevai.example.com/fullchain.pem docker/nginx/certs/
sudo cp /etc/letsencrypt/live/custdevai.example.com/privkey.pem docker/nginx/certs/
sudo chown custdev:custdev docker/nginx/certs/*

# 3. Каталог для renew-challenge (Phase 6: автообновление через certbot-renew).
mkdir -p docker/nginx/certbot-www
```

Для автообновления настроим cron позже (см. §10).

## 7. Сборка и первый запуск

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml build
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Проверка статусов:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail 50 api
```

Все сервисы должны быть `running` / `healthy`.

## 8. Миграции БД + bootstrap admin

```bash
# Применить все Alembic-ревизии (0001..0005).
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api \
    alembic upgrade head

# Создать первого администратора (FR-AUTH-01).
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api \
    python -m apps.api.cli create-admin \
    --email admin@custdevai.example.com \
    --password "$(openssl rand -base64 24)"

# Скопировать выведенный пароль в безопасное место.
```

## 9. Регистрация Telegram webhook

```bash
TOKEN=$(grep ^TELEGRAM_BOT_TOKEN .env | cut -d= -f2)
SECRET=$(grep ^TELEGRAM_WEBHOOK_SECRET .env | cut -d= -f2)

curl -fsS -X POST \
    "https://api.telegram.org/bot${TOKEN}/setWebhook" \
    -F "url=https://custdevai.example.com/api/v1/telegram/webhook" \
    -F "secret_token=${SECRET}" \
    -F "allowed_updates=[\"message\",\"callback_query\"]"
```

Ответ должен быть `{"ok":true,"result":true}`.

## 10. Smoke-test после деплоя

```bash
# 1. /health возвращает 200.
curl -fsS https://custdevai.example.com/health
# {"status":"ok"}

# 2. Логин админа через cookie auth.
curl -fsS -c cookies.txt \
    -X POST "https://custdevai.example.com/api/v1/auth/login?set_cookie=true" \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@custdevai.example.com","password":"..."}'

# 3. /me возвращает профиль.
curl -fsS -b cookies.txt https://custdevai.example.com/api/v1/users/me

# 4. Откройте SPA в браузере: https://custdevai.example.com
#    Войти, создать тестовый сценарий, создать кампанию, нажать «Создать»,
#    активировать кампанию, получить ссылку-приглашение бота.

# 5. Пройти полный цикл интервью через Telegram → дождаться analyze_campaign
#    (Celery worker) → скачать PDF в SPA.

# 6. Проверить ежедневный backup готов:
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec worker \
    celery -A apps.worker.celery_app call backup.database
# Затем убедиться, что файл создался в /var/lib/custdevai/backups.
```

## 11. Renew Let's Encrypt (запланировано)

```bash
sudo crontab -e
```

Добавить строку:

```
0 3 * * 1 certbot renew --deploy-hook "docker compose -f /home/custdev/custdevai/docker-compose.yml -f /home/custdev/custdevai/docker-compose.prod.yml restart web"
```

Каждый понедельник в 03:00 UTC certbot проверяет, не пора ли обновлять;
обновляет за 30 дней до истечения; nginx перезапускается через web сервис.

## 12. Мониторинг и логи

В production без выделенного ELK / Loki — простой просмотр:

```bash
# Tail логов api.
docker compose logs -f --tail 100 api

# Логи bot.
docker compose logs -f --tail 100 bot

# Логи worker (включая celery beat backup, sweeper).
docker compose logs -f --tail 100 worker worker-beat
```

Опционально — Sentry: установить `SENTRY_DSN` в `.env`, сервисы подхватят.

## 13. Откат при проблемах

```bash
# Сделать новый backup до отката.
docker compose exec worker celery -A apps.worker.celery_app call backup.database

# Зафиксировать текущий тэг git для возврата.
git tag pre-rollback

# Откат на предыдущую успешную ревизию.
git checkout <previous_commit>
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Откат миграции (если новая ломает схему).
docker compose exec api alembic downgrade <previous_revision_id>
```

При полной потере БД — см. `docs/DISASTER_RECOVERY.md` процедура §3.

## 14. Checklist для защиты ВКР

- [ ] CI на main зелёный (`pytest -m "not ml"`, ruff, mypy).
- [ ] Production-стенд развёрнут (HTTPS работает, certbot активен).
- [ ] Bootstrap admin создан.
- [ ] Telegram webhook зарегистрирован.
- [ ] Backup-таск выполнялся хотя бы один раз; файл в /var/lib/custdevai/backups.
- [ ] Demo-сценарий пройден end-to-end (бот → анализ → отчёт).
- [ ] ML_METRICS.md заполнен фактическими числами после fine-tune.
- [ ] LOAD_TEST_REPORT.md заполнен фактическими p95/wall-time.
- [ ] DISASTER_RECOVERY.md §4 заполнен фактическим RTO.
- [ ] BROWSER_QA_REPORT.md (если SHOULD-10 успевает).

## 15. Что не входит в эту процедуру

- WAL-archiving / PITR (Phase 6).
- Горизонтальное масштабирование worker (через docker-compose `--scale worker=N`).
- Geo-redundancy / multi-region (Phase 6).
- CDN перед Nginx (Phase 6).
- Кубернетес-манифесты (Phase 6).
