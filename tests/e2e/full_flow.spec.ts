/**
 * E2E full-flow тест (FR-WEB-01..11, NFR-OPS-05).
 *
 * Сценарий:
 *   1. Открыть SPA → 302 на /login.
 *   2. Заполнить форму логина → cookie auth → редирект на /.
 *   3. Зайти на /scripts/new → создать сценарий с 2 вопросами.
 *   4. Зайти на /campaigns/new → выбрать сценарий → создать кампанию.
 *   5. Открыть /campaigns/:id → проверить отображение метаданных.
 *   6. Проверить отображение SettingsPage (researcher chat_id).
 *
 * Тест запускается с переменными:
 *   E2E_BASE_URL   — URL SPA (default https://localhost).
 *   E2E_LOGIN      — email админа.
 *   E2E_PASSWORD   — пароль админа.
 */

import { test, expect } from "@playwright/test";

const LOGIN = process.env.E2E_LOGIN ?? "admin@custdevai.example.com";
const PASSWORD = process.env.E2E_PASSWORD ?? "ChangeMe-secure-1!";

test.describe("CustDevAI SPA — full researcher flow", () => {
  test("login → script → campaign → settings @1024x768", async ({ page }) => {
    // 1. Главная → редирект на /login.
    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.locator("h2", { hasText: /Вход в панель/ })).toBeVisible();

    // 2. Логин.
    await page.fill('input[type="email"]', LOGIN);
    await page.fill('input[type="password"]', PASSWORD);
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL("/");
    await expect(page.locator("h2", { hasText: "Кампании" })).toBeVisible();

    // 3. Новый сценарий.
    await page.click('a[href="/scripts/new"]');
    await page.fill('input[name="title"]', "E2E sanity script");
    // Первый вопрос.
    await page.fill('textarea[name="questions.0.text"]', "Какую проблему вы решаете?");
    // Добавить второй вопрос.
    await page.click('button:has-text("+ Добавить вопрос")');
    await page.fill('textarea[name="questions.1.text"]', "Какие альтернативы пробовали?");
    await page.click('button[type="submit"]:has-text("Сохранить")');
    await expect(page).toHaveURL(/\/scripts\/\d+/);

    // 4. Новая кампания.
    await page.goto("/campaigns/new");
    await page.fill('input[name="title"]', "E2E test campaign");
    await page.selectOption("select#script_id", { label: /E2E sanity script/ });
    await page.click('button[type="submit"]:has-text("Создать")');
    await expect(page).toHaveURL(/\/campaigns\/\d+/);
    await expect(page.locator(".badge.draft")).toBeVisible();

    // 5. Настройки профиля.
    await page.goto("/settings");
    await expect(
      page.locator("h2", { hasText: /Настройки профиля/ }),
    ).toBeVisible();
    await expect(page.locator("input[type=email]")).toBeDisabled();

    // 6. Проверка адаптивности — на 1024×768 не должно быть
    // горизонтального скролла основного контента.
    const { scrollWidth, clientWidth } = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 2);
  });
});
