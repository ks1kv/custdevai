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
  useState,
  type ReactNode,
} from "react";

import { ApiError, apiRequest } from "@/api/client";
import type { TokenPair, UserOut } from "@/api/types";

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

  useEffect(() => {
    let cancelled = false;
    fetchMe()
      .then((u) => {
        if (!cancelled) setUser(u);
      })
      .catch(() => {
        if (!cancelled) setUser(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [fetchMe]);

  const login = useCallback(
    async (email: string, password: string) => {
      // ?set_cookie=true — API выставит httpOnly access/refresh cookies.
      await apiRequest<TokenPair>("/api/v1/auth/login?set_cookie=true", {
        method: "POST",
        body: { email, password },
      });
      const profile = await fetchMe();
      if (!profile) throw new Error("Не удалось получить профиль после входа");
      setUser(profile);
      return profile;
    },
    [fetchMe],
  );

  const logout = useCallback(async () => {
    try {
      await apiRequest("/api/v1/auth/logout", { method: "POST" });
    } catch {
      /* всё равно очищаем локальное состояние */
    }
    setUser(null);
  }, []);

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
