/**
 * NFR-PRF-01 / NFR-PRF-06 — 50 параллельных Telegram-сессий через webhook.
 *
 * Каждый виртуальный пользователь имитирует одного респондента: посылает
 * /start с deep-link, согласие, ответы на вопросы. Замеряется p95
 * времени HTTP-ответа FastAPI-эндпоинта /api/v1/telegram/webhook —
 * именно этот показатель отражает "время отклика бота" (FR-NFR-PRF-01),
 * поскольку aiogram внутри webhook обрабатывает update полностью до
 * возврата response.
 *
 * Запуск:
 *   export API_BASE=http://localhost:8000
 *   export WEBHOOK_SECRET=<TELEGRAM_WEBHOOK_SECRET из .env>
 *   export CAMPAIGN_ID=1   # должна существовать active-кампания
 *   k6 run tests/load/scenario_1_bot_webhook.js
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Trend, Counter } from "k6/metrics";

const API_BASE = __ENV.API_BASE || "http://localhost:8000";
const WEBHOOK_SECRET = __ENV.WEBHOOK_SECRET || "";
const CAMPAIGN_ID = parseInt(__ENV.CAMPAIGN_ID || "1", 10);
const VUS = parseInt(__ENV.VUS || "50", 10);
const DURATION = __ENV.DURATION || "60s";

export const options = {
  vus: VUS,
  duration: DURATION,
  thresholds: {
    // NFR-PRF-01: ≤ 3 секунды на 50 сессиях.
    "http_req_duration{phase:webhook}": ["p(95)<3000"],
    http_req_failed: ["rate<0.01"],
  },
  tags: { scenario: "bot_webhook_50par" },
};

const webhookLatency = new Trend("webhook_latency", true);
const flowsCompleted = new Counter("flows_completed");

function fakeUpdate(updateId, chatId, text, startPayload = null) {
  const message = {
    message_id: updateId,
    date: Math.floor(Date.now() / 1000),
    chat: { id: chatId, type: "private", first_name: `R${chatId}` },
    from: { id: chatId, is_bot: false, first_name: `R${chatId}` },
    text,
  };
  if (startPayload) {
    // /start с deep-link payload: текст вида "/start c<campaign_id>"
    message.text = `/start ${startPayload}`;
    message.entities = [{ type: "bot_command", offset: 0, length: 6 }];
  }
  return { update_id: updateId, message };
}

function sendWebhook(payload) {
  const r = http.post(`${API_BASE}/api/v1/telegram/webhook`, JSON.stringify(payload), {
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET,
    },
    tags: { phase: "webhook" },
  });
  webhookLatency.add(r.timings.duration);
  return r;
}

export default function () {
  const chatId = 1_000_000 + __VU * 1000 + __ITER;
  let updateId = chatId * 100;

  // /start с deep-link
  let r = sendWebhook(fakeUpdate(++updateId, chatId, "", `c${CAMPAIGN_ID}`));
  check(r, { "start ok": (resp) => resp.status === 200 });
  sleep(Math.random() * 0.5 + 0.5);

  // Согласие — callback-кнопка не имитируется в JS-сценарии; для нагрузки
  // достаточно повторных текстовых апдейтов как fallback. На реальной
  // системе согласие даётся через inline_keyboard callback_query;
  // в боте это ветка, обрабатывающая аналогичную нагрузку.
  r = sendWebhook(fakeUpdate(++updateId, chatId, "Согласен"));
  check(r, { "consent ok": (resp) => resp.status === 200 });
  sleep(Math.random() * 0.5 + 0.3);

  // 5 ответов на вопросы.
  for (let i = 0; i < 5; i++) {
    r = sendWebhook(
      fakeUpdate(
        ++updateId,
        chatId,
        `Ответ респондента ${chatId} на вопрос ${i + 1}: тестовая нагрузка нагрузочного теста.`,
      ),
    );
    check(r, { [`answer_${i + 1} ok`]: (resp) => resp.status === 200 });
    sleep(Math.random() * 1.5 + 0.5);
  }

  flowsCompleted.add(1);
}
