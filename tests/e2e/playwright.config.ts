/**
 * Playwright cross-browser config — FR-WEB-12, NFR-OPS-05.
 *
 * Профили:
 *   - chromium-1024: Chrome 110+ через chromium engine, viewport 1024×768.
 *   - firefox-1024: Firefox 110+ через firefox engine, viewport 1024×768.
 *   - yandex-1024: Yandex Browser через chromium engine (он тоже Blink) с
 *                  Yandex-User-Agent, viewport 1024×768.
 *
 * Минимальный viewport 1024×768 соответствует требованию адаптивной
 * вёрстки (FR-WEB-12). Если страница ломается на этом разрешении —
 * тест падает с screenshot.
 */

import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.E2E_BASE_URL ?? "https://localhost";
const yandexUA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/120.0.0.0 YaBrowser/24.1.0.0 Safari/537.36";

export default defineConfig({
  testDir: ".",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1, // последовательно, чтобы не конкурировать за демо-сценарий
  reporter: [
    ["html", { outputFolder: "playwright-report" }],
    ["list"],
  ],
  use: {
    baseURL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    ignoreHTTPSErrors: true, // для self-signed dev-certs
  },
  projects: [
    {
      name: "chromium-1024",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1024, height: 768 },
      },
    },
    {
      name: "firefox-1024",
      use: {
        ...devices["Desktop Firefox"],
        viewport: { width: 1024, height: 768 },
      },
    },
    {
      name: "yandex-1024",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1024, height: 768 },
        userAgent: yandexUA,
      },
    },
  ],
});
