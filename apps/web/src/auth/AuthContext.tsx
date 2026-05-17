/**
 * AuthContext — обёртка httpOnly cookie auth. SPA не хранит токены сама,
 * вместо этого опирается на cookies, выставленные API при логине
 * (?set_cookie=true). Экран Login вызывает login(), который дёргает
 * /auth/login и затем GET /users/me, чтобы получить профиль.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { ApiError, apiRequest, refreshTokens } from "@/api/client";
import type { TokenPair, UserOut } from "@/api/types";

// За сколько секунд до истечения access-токена дёргать /auth/refresh.
// 60 с — достаточный буфер на сетевые задержки и приостановку таймера
// в неактивных вкладках без избыточных вызовов.
const REFRESH_LEAD_SECONDS = 60;
const MIN_REFRESH_INTERVAL_MS = 30_000;
// Fallback, если бэк не вернул expires_in (старая версия API):
// дёргаем refresh каждые 14 минут — это меньше захардкоженных 15 на бэке.
const FALLBACK_REFRESH_INTERVAL_MS = 14 * 60 * 1000;

interface AuthState {
  user: UserOut | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<UserOut>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null);
  const [loading, setLoading] = useState(true);

  // Таймер проактивного refresh. Перезапускается после каждого успешного
  // refresh с актуальным expires_in от бэка. Очищается при logout или
  // когда AuthProvider размонтируется.
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchMe = useCallback(async (): Promise<UserOut | null> => {
    try {
      return await apiRequest<UserOut>("/api/v1/users/me");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        return null;
      }
      throw err;
    }
  }, []);

  const clearRefreshTimer = useCallback(() => {
    if (refreshTimerRef.current !== null) {
      clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
  }, []);

  const scheduleProactiveRefresh = useCallback(
    (expiresInSeconds: number | undefined) => {
      clearRefreshTimer();
      const delayMs =
        expiresInSeconds && expiresInSeconds > REFRESH_LEAD_SECONDS
          ? Math.max(
              MIN_REFRESH_INTERVAL_MS,
              (expiresInSeconds - REFRESH_LEAD_SECONDS) * 1000,
            )
          : FALLBACK_REFRESH_INTERVAL_MS;
      refreshTimerRef.current = setTimeout(async () => {
        const tokens = await refreshTokens();
        if (tokens) {
          // Рекурсивно перезапускаем с новым expires_in от свежего ответа.
          scheduleProactiveRefresh(tokens.expires_in);
        } else {
          // refresh не прошёл — пусть следующий 401 даст явный logout
          // через fetchWithAuthRetry. Таймер не перезапускаем.
          refreshTimerRef.current = null;
        }
      }, delayMs);
    },
    [clearRefreshTimer],
  );

  useEffect(() => {
    let cancelled = false;
    fetchMe()
      .then((u) => {
        if (cancelled) return;
        setUser(u);
        if (u) {
          // Если активная сессия есть, но мы не знаем точный TTL access-
          // токена (страница перезагружена), используем fallback-интервал.
          scheduleProactiveRefresh(undefined);
        }
      })
      .catch(() => {
        if (!cancelled) setUser(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
      clearRefreshTimer();
    };
  }, [fetchMe, scheduleProactiveRefresh, clearRefreshTimer]);

  const login = useCallback(
    async (email: string, password: string) => {
      // ?set_cookie=true — API выставит httpOnly access/refresh cookies.
      const tokens = await apiRequest<TokenPair>(
        "/api/v1/auth/login?set_cookie=true",
        { method: "POST", body: { email, password } },
      );
      const profile = await fetchMe();
      if (!profile) throw new Error("Не удалось получить профиль после входа");
      setUser(profile);
      scheduleProactiveRefresh(tokens.expires_in);
      return profile;
    },
    [fetchMe, scheduleProactiveRefresh],
  );

  const logout = useCallback(async () => {
    clearRefreshTimer();
    try {
      await apiRequest("/api/v1/auth/logout", { method: "POST" });
    } catch {
      /* всё равно очищаем локальное состояние */
    }
    setUser(null);
  }, [clearRefreshTimer]);

  const refresh = useCallback(async () => {
    const profile = await fetchMe();
    setUser(profile);
  }, [fetchMe]);

  const value = useMemo<AuthState>(
    () => ({ user, loading, login, logout, refresh }),
    [user, loading, login, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth должен использоваться внутри AuthProvider");
  return ctx;
}
