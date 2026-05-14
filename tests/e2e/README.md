# E2E browser-тесты CustDevAI (FR-WEB-12, NFR-OPS-05)

Playwright-сценарии для кросс-браузерной проверки SPA. Три профиля:

| Профиль | Движок | UA / Версия | Viewport |
|---|---|---|---|
| `chromium-1024` | chromium | Desktop Chrome | 1024×768 |
| `firefox-1024` | firefox | Desktop Firefox | 1024×768 |
| `yandex-1024` | chromium (Blink) | UA Yandex Browser 24 | 1024×768 |

Yandex Browser использует chromium-engine (как сам Yandex), поэтому
визуально и поведенчески неотличим от Chrome — UA-override нужен только
для случаев условной логики по UA-строке (в нашем SPA таких нет).

## Установка

```bash
cd tests/e2e
npm install
npm run install-browsers   # скачивает chromium, firefox, ~500 МБ
```

## Запуск

Перед запуском убедиться, что:
- Production-стенд развёрнут (см. `docs/DEPLOYMENT.md`).
- Bootstrap admin создан и его логин/пароль доступны через ENV.
- TLS-сертификат валиден или `ignoreHTTPSErrors: true` (default).

```bash
export E2E_BASE_URL=https://custdevai.example.com
export E2E_LOGIN=admin@custdevai.example.com
export E2E_PASSWORD=...

# Все три профиля.
npm test

# Один профиль для быстрой итерации.
npm run test:chromium
npm run test:firefox
npm run test:yandex

# HTML-отчёт со скриншотами.
npm run report
```

## Что проверяется в full_flow.spec.ts

1. Редирект `/` → `/login` для неавторизованного пользователя.
2. Логин через cookie-auth, редирект на дашборд.
3. Создание сценария с 2 вопросами через ScriptBuilderPage (FR-WEB-01).
4. Создание кампании с привязкой сценария.
5. Открытие SettingsPage (researcher chat_id регистрация).
6. Отсутствие горизонтального скролла на 1024×768 (FR-WEB-12).

При неудаче — screenshot в `playwright-report/`.

## Сводный отчёт

После прогона всех профилей результаты заносятся в
`docs/BROWSER_QA_REPORT.md` со скриншотами и заметками о
браузер-специфичных различиях.
