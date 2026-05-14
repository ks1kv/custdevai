# Cross-browser QA report (FR-WEB-12, NFR-OPS-05)

Документирует результаты ручного + автоматизированного тестирования
SPA CustDevAI в трёх целевых браузерах. Тест-сценарий —
`tests/e2e/full_flow.spec.ts` (Playwright).

## Целевые версии

| Браузер | Минимальная версия | Источник |
|---|---|---|
| Google Chrome | 110+ | NFR-OPS-05 (docs/03_requirements_specification.md) |
| Mozilla Firefox | 110+ | NFR-OPS-05 |
| Yandex Browser | 23+ | NFR-OPS-05 |

Минимальное разрешение: **1024×768** (FR-WEB-12).

## Запуск

```bash
cd tests/e2e
npm install
npm run install-browsers

export E2E_BASE_URL=https://custdevai.example.com
export E2E_LOGIN=admin@custdevai.example.com
export E2E_PASSWORD=...
npm test
```

## Результаты по профилям

### Chromium 1024×768 (имитирует Chrome 110+)

| Сценарий | Статус | Заметки |
|---|---|---|
| LoginPage → редирект `/` | _TBD_ | — |
| ScriptBuilderPage (FR-WEB-01) | _TBD_ | — |
| CampaignCreatePage (FR-WEB-04) | _TBD_ | — |
| CampaignDetailPage (FR-WEB-05) | _TBD_ | — |
| SettingsPage chat_id | _TBD_ | — |
| Горизонтальный скролл на 1024×768 | _TBD_ | scrollWidth ≤ clientWidth |
| Скриншоты | `tests/e2e/playwright-report/chromium-1024/*.png` | — |

### Firefox 1024×768

| Сценарий | Статус | Заметки |
|---|---|---|
| LoginPage → редирект `/` | _TBD_ | — |
| ScriptBuilderPage (FR-WEB-01) | _TBD_ | — |
| CampaignCreatePage | _TBD_ | — |
| CampaignDetailPage | _TBD_ | — |
| SettingsPage chat_id | _TBD_ | — |
| Горизонтальный скролл на 1024×768 | _TBD_ | — |
| Скриншоты | `tests/e2e/playwright-report/firefox-1024/*.png` | — |

### Yandex Browser 1024×768 (chromium-engine + UA override)

| Сценарий | Статус | Заметки |
|---|---|---|
| LoginPage → редирект `/` | _TBD_ | — |
| ScriptBuilderPage (FR-WEB-01) | _TBD_ | — |
| CampaignCreatePage | _TBD_ | — |
| CampaignDetailPage | _TBD_ | — |
| SettingsPage chat_id | _TBD_ | — |
| Горизонтальный скролл на 1024×768 | _TBD_ | — |
| Скриншоты | `tests/e2e/playwright-report/yandex-1024/*.png` | — |

## Известные различия между браузерами

_Заполняется по факту прогона. Ожидается: SPA построен на React 18 + TS
+ Recharts без браузер-специфичной логики, поэтому различия должны
сводиться к стилевым деталям._

| Элемент | Chrome | Firefox | Yandex |
|---|---|---|---|
| `<select>` оформление | _TBD_ | _TBD_ | _TBD_ |
| Скроллбары | _TBD_ | _TBD_ | _TBD_ |
| Шрифтовой рендер | _TBD_ | _TBD_ | _TBD_ |
| Recharts SVG-сглаживание | _TBD_ | _TBD_ | _TBD_ |

## Соответствие требованиям

| Требование | Тест | Статус |
|---|---|---|
| FR-WEB-12 — работа на 1024×768 | scrollWidth ≤ clientWidth check | _TBD_ |
| NFR-OPS-05 — Chrome 110+ / FF 110+ / Yandex 23+ | full_flow.spec в каждом профиле | _TBD_ |

## Если тест падает

1. Скриншот сохраняется в `tests/e2e/playwright-report/`.
2. Trace включён на retry — открыть `npm run report` для timeline.
3. Анализировать, является ли проблема:
   - **CSS** (browser-specific) — фиксить через autoprefixer / fallback;
   - **JS API** (несовместимая фича) — добавить polyfill / vite plugin;
   - **shadcn UI primitive** — обновить версию Radix.
