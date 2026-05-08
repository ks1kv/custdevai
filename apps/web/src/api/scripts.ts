import { apiRequest } from "./client";
import type { Page, ScriptCreate, ScriptOut } from "./types";

export function listScripts(params: { q?: string; limit?: number; offset?: number }) {
  return apiRequest<Page<ScriptOut>>("/api/v1/scripts", { query: params });
}

export function getScript(id: number) {
  return apiRequest<ScriptOut>(`/api/v1/scripts/${id}`);
}

export function createScript(payload: ScriptCreate) {
  return apiRequest<ScriptOut>("/api/v1/scripts", { method: "POST", body: payload });
}

export function updateScript(id: number, payload: Partial<ScriptCreate>) {
  return apiRequest<ScriptOut>(`/api/v1/scripts/${id}`, {
    method: "PATCH",
    body: payload,
  });
}

export function deleteScript(id: number) {
  return apiRequest<void>(`/api/v1/scripts/${id}`, { method: "DELETE" });
}
