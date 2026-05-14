/**
 * NFR-PRF-02 / NFR-PRF-08 — 1000 параллельных GET-запросов к /api/v1/campaigns.
 *
 * Замеряем p95 латентности типового read-эндпоинта при нагрузке 1000 RPS.
 * Целевое NFR-PRF-08: p95 ≤ 200 мс. NFR-PRF-02: ≤ 3 с на 1000 записей в
 * таблице — этот же эндпоинт с page-size=100 покрывает.
 *
 * Перед запуском в БД должна быть seed-нагрузка не менее 1000 кампаний
 * (можно создать через `python -m tests.load.scenario_2_ml_analyze`
 * с флагом `--seed-campaigns 1000`).
 *
 * Запуск:
 *   export API_BASE=http://localhost:8000
 *   export AUTH_TOKEN=<JWT access token>
 *   k6 run tests/load/scenario_4_api_read.js
 */

import http from "k6/http";
import { check } from "k6";
import { Trend } from "k6/metrics";

const API_BASE = __ENV.API_BASE || "http://localhost:8000";
const AUTH_TOKEN = __ENV.AUTH_TOKEN || "";

export const options = {
  scenarios: {
    steady_1000_rps: {
      executor: "constant-arrival-rate",
      rate: 1000,
      timeUnit: "1s",
      duration: "30s",
      preAllocatedVUs: 100,
      maxVUs: 500,
    },
  },
  thresholds: {
    "http_req_duration{endpoint:campaigns_list}": ["p(95)<200"],
    http_req_failed: ["rate<0.01"],
  },
  tags: { scenario: "api_read_1000rps" },
};

const apiLatency = new Trend("api_latency", true);

export default function () {
  const r = http.get(`${API_BASE}/api/v1/campaigns?limit=100`, {
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${AUTH_TOKEN}`,
    },
    tags: { endpoint: "campaigns_list" },
  });
  apiLatency.add(r.timings.duration);
  check(r, {
    "status 200": (resp) => resp.status === 200,
    "has items": (resp) => {
      try {
        return JSON.parse(resp.body).items !== undefined;
      } catch {
        return false;
      }
    },
  });
}
