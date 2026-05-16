/**
 * fetch-обёртка для API CustDevAI. httpOnly cookies автоматически
 * передаются через `credentials: "include"`. RFC 7807 ошибки
 * парсятся в ApiError.
 */

import type { ProblemDetail } from "./types";

export class ApiError extends Error {
  status: number;
  problem: ProblemDetail;

  constructor(problem: ProblemDetail) {
    super(problem.detail || problem.title);
    this.status = problem.status;
    this.problem = problem;
  }
}

// В production SPA и API живут на одном origin: nginx (web-контейнер)
// проксирует /api/* на FastAPI. Поэтому по умолчанию API_BASE пустой —
// все вызовы становятся same-origin относительными путями /api/v1/...
// Для локального dev (Vite на :5173, API на :8000) задаётся через .env:
//   VITE_API_BASE_URL=http://localhost:8000
const API_BASE = (import.meta as unknown as { env: { VITE_API_BASE_URL?: string } })
  .env.VITE_API_BASE_URL ?? "";

function buildUrl(path: string): URL {
  // Если API_BASE пустой — same-origin: используем window.location.origin
  // как базу, чтобы new URL() не упал на относительном пути.
  return API_BASE ? new URL(`${API_BASE}${path}`) : new URL(path, window.location.origin);
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined>;
  signal?: AbortSignal;
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = "GET", body, query, signal } = options;
  const url = buildUrl(path);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined) continue;
      url.searchParams.set(k, String(v));
    }
  }

  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const res = await fetch(url.toString(), {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: "include",
    signal,
  });

  if (res.status === 204) return undefined as T;

  // application/problem+json — RFC 7807. Парсим как JSON-ошибку.
  const contentType = res.headers.get("Content-Type") || "";
  if (!res.ok) {
    if (contentType.includes("problem+json") || contentType.includes("json")) {
      const problem = (await res.json()) as ProblemDetail;
      throw new ApiError(problem);
    }
    throw new ApiError({
      type: "about:blank",
      title: "Ошибка сети",
      status: res.status,
    });
  }
  if (contentType.includes("json")) {
    return (await res.json()) as T;
  }
  // Бинарный ответ (отчёт PDF/XLSX) — вызывающий код будет
  // использовать blob() напрямую через apiBlob().
  return (await res.text()) as unknown as T;
}

export async function apiBlob(path: string, options: RequestOptions = {}): Promise<Blob> {
  const { method = "GET", query, signal } = options;
  const url = buildUrl(path);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined) continue;
      url.searchParams.set(k, String(v));
    }
  }
  const res = await fetch(url.toString(), {
    method,
    credentials: "include",
    signal,
  });
  if (!res.ok) {
    let problem: ProblemDetail = {
      type: "about:blank",
      title: "Ошибка скачивания",
      status: res.status,
    };
    try {
      problem = (await res.json()) as ProblemDetail;
    } catch {
      /* нет JSON — оставляем заглушку */
    }
    throw new ApiError(problem);
  }
  return await res.blob();
}
