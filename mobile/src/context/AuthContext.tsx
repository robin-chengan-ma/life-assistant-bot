import {
  createContext,
  type PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { AppState } from "react-native";

import {
  ApiError,
  type AppUser,
  type AppPreferences,
  apiRequest,
  forgotPassword as requestPasswordReset,
  identifyUser as requestIdentifyUser,
  login as requestLogin,
  logout as requestLogout,
  refreshSession as requestRefresh,
} from "@/services/authApi";
import {
  clearRefreshToken,
  getRefreshToken,
  saveRefreshToken,
} from "@/services/tokenStorage";

type AuthStatus = "loading" | "guest" | "authenticated";

type AuthContextValue = {
  status: AuthStatus;
  user: AppUser | null;
  login: (userId: string, password: string, keepLoggedIn: boolean) => Promise<string>;
  forgotPassword: (userId: string) => Promise<string>;
  identifyUser: (userId: string) => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<string>;
  updatePreferences: (preferences: AppPreferences) => Promise<string>;
  logout: () => Promise<void>;
  authorizedRequest: <T>(path: string, options?: RequestInit) => Promise<T>;
  clearLoginNotice: () => void;
  loginNotice: string | null;
};

const AuthContext = createContext<AuthContextValue | null>(null);
const REFRESH_EARLY_SECONDS = 60;

export function AuthProvider({ children }: PropsWithChildren) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<AppUser | null>(null);
  const [accessTokenExpiresAt, setAccessTokenExpiresAt] = useState<number | null>(null);
  const [hasRefreshToken, setHasRefreshToken] = useState(false);
  const [loginNotice, setLoginNotice] = useState<string | null>(null);
  const accessTokenRef = useRef<string | null>(null);

  const clearSession = useCallback(async () => {
    accessTokenRef.current = null;
    setAccessTokenExpiresAt(null);
    setHasRefreshToken(false);
    setLoginNotice(null);
    setUser(null);
    setStatus("guest");
    await clearRefreshToken();
  }, []);

  const applySession = useCallback(
    async (
      accessToken: string,
      accessTokenExpiresIn: number,
      nextUser: AppUser,
      refreshToken: string | null,
    ) => {
      accessTokenRef.current = accessToken;
      setAccessTokenExpiresAt(Date.now() + accessTokenExpiresIn * 1000);
      setHasRefreshToken(Boolean(refreshToken));
      setUser(nextUser);
      setStatus("authenticated");
      if (refreshToken) {
        await saveRefreshToken(refreshToken);
      }
    },
    [],
  );

  const refreshSession = useCallback(async (): Promise<boolean> => {
    const storedRefreshToken = await getRefreshToken();
    if (!storedRefreshToken) {
      return false;
    }
    try {
      const session = await requestRefresh(storedRefreshToken);
      await applySession(
        session.access_token,
        session.access_token_expires_in,
        session.user,
        session.refresh_token,
      );
      return true;
    } catch {
      await clearSession();
      return false;
    }
  }, [applySession, clearSession]);

  useEffect(() => {
    void (async () => {
      const restored = await refreshSession();
      if (!restored) {
        setStatus("guest");
      }
    })();
  }, [refreshSession]);

  useEffect(() => {
    if (status !== "authenticated" || accessTokenExpiresAt === null) {
      return undefined;
    }

    const sessionEndAt = hasRefreshToken
      ? accessTokenExpiresAt - REFRESH_EARLY_SECONDS * 1000
      : accessTokenExpiresAt;
    const delay = Math.max(0, sessionEndAt - Date.now());
    const timer = setTimeout(() => {
      if (hasRefreshToken) {
        void refreshSession();
        return;
      }
      void clearSession();
    }, delay);
    return () => clearTimeout(timer);
  }, [accessTokenExpiresAt, clearSession, hasRefreshToken, refreshSession, status]);

  useEffect(() => {
    const subscription = AppState.addEventListener("change", (nextState) => {
      if (
        nextState === "active" &&
        status === "authenticated" &&
        accessTokenExpiresAt !== null &&
        Date.now() >=
          accessTokenExpiresAt - (hasRefreshToken ? REFRESH_EARLY_SECONDS * 1000 : 0)
      ) {
        if (hasRefreshToken) {
          void refreshSession();
        } else {
          void clearSession();
        }
      }
    });
    return () => subscription.remove();
  }, [accessTokenExpiresAt, clearSession, hasRefreshToken, refreshSession, status]);

  const login = useCallback(
    async (userId: string, password: string, keepLoggedIn: boolean) => {
      const session = await requestLogin(userId, password, keepLoggedIn);
      if (!keepLoggedIn) {
        await clearRefreshToken();
      }
      await applySession(
        session.access_token,
        session.access_token_expires_in,
        session.user,
        session.refresh_token,
      );
      setLoginNotice(session.message);
      return session.message;
    },
    [applySession],
  );

  const forgotPassword = useCallback(async (userId: string) => {
    const response = await requestPasswordReset(userId);
    return response.message;
  }, []);

  const identifyUser = useCallback(async (userId: string) => {
    await requestIdentifyUser(userId);
  }, []);

  const clearLoginNotice = useCallback(() => setLoginNotice(null), []);

  const logout = useCallback(async () => {
    const accessToken = accessTokenRef.current;
    try {
      if (accessToken) {
        await requestLogout(accessToken);
      }
    } catch {
      // 後端暫時不可用時仍必須完成本機登出，避免使用者被卡在登入狀態。
    } finally {
      await clearSession();
    }
  }, [clearSession]);

  const authorizedRequest = useCallback(
    async <T,>(path: string, options: RequestInit = {}): Promise<T> => {
      const execute = () => {
        const accessToken = accessTokenRef.current;
        if (!accessToken) {
          throw new ApiError("請先登入", 401);
        }
        return apiRequest<T>(path, {
          ...options,
          headers: {
            ...options.headers,
            Authorization: `Bearer ${accessToken}`,
          },
        });
      };

      try {
        return await execute();
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 401) {
          throw error;
        }
        const refreshed = await refreshSession();
        if (!refreshed) {
          throw error;
        }
        return execute();
      }
    },
    [refreshSession],
  );

  const changePassword = useCallback(
    async (currentPassword: string, newPassword: string) => {
      const response = await authorizedRequest<{ message: string }>(
        "/api/app/auth/change-password",
        {
          method: "POST",
          body: JSON.stringify({
            current_password: currentPassword,
            new_password: newPassword,
          }),
        },
      );
      await clearSession();
      setLoginNotice(response.message);
      return response.message;
    },
    [authorizedRequest, clearSession],
  );

  const updatePreferences = useCallback(
    async (preferences: AppPreferences) => {
      const response = await authorizedRequest<{ message: string; user: AppUser }>(
        "/api/app/auth/preferences",
        { method: "POST", body: JSON.stringify(preferences) },
      );
      setUser(response.user);
      return response.message;
    },
    [authorizedRequest],
  );

  return (
    <AuthContext.Provider
      value={{
        status,
        user,
        login,
        forgotPassword,
        identifyUser,
        changePassword,
        updatePreferences,
        logout,
        authorizedRequest,
        clearLoginNotice,
        loginNotice,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth 必須在 AuthProvider 內使用");
  }
  return context;
}
