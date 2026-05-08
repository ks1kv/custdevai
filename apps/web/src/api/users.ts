import { apiRequest } from "./client";
import type { MyProfileUpdate, UserOut } from "./types";

export function getMe() {
  return apiRequest<UserOut>("/api/v1/users/me");
}

export function updateMe(payload: MyProfileUpdate) {
  return apiRequest<UserOut>("/api/v1/users/me", { method: "PATCH", body: payload });
}
