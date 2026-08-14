export type AppUser = {
  database_id: number;
  user_id: string;
  role: string;
  is_owner: boolean;
  gender: "male" | "female" | null;
  previous_login_at: string | null;
  current_login_at: string | null;
  password_changed_at: string | null;
  theme_preference: "light" | "dark";
  font_size_preference: "small" | "medium" | "large";
  privacy_mask_enabled: boolean;
};

export type AppPreferences = Pick<
  AppUser,
  "theme_preference" | "font_size_preference" | "privacy_mask_enabled"
>;

export type AuthSessionResponse = {
  message: string;
  access_token: string;
  access_token_expires_in: number;
  refresh_token: string | null;
  user: AppUser;
};

type ApiErrorBody = {
  code?: string;
  message?: string;
};

const configuredApiBaseUrl = (
  process.env.EXPO_PUBLIC_API_BASE_URL ?? "http://localhost:8080"
).replace(/\/$/, "");
const isLocalWebPreview = Platform.OS === "web"
  && typeof window !== "undefined"
  && ["localhost", "127.0.0.1"].includes(window.location.hostname);
const apiBaseUrl = Platform.OS === "web" && typeof window !== "undefined" && !isLocalWebPreview
  ? window.location.origin
  : configuredApiBaseUrl;

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
    });
  } catch {
    throw new ApiError("目前無法連線，請確認網路後再試", 0);
  }

  const body = (await response.json().catch(() => ({}))) as ApiErrorBody;
  if (!response.ok) {
    throw new ApiError(body.message ?? "操作失敗，請稍後再試", response.status, body.code);
  }
  return body as T;
}

export function login(
  userId: string,
  password: string,
  keepLoggedIn: boolean,
): Promise<AuthSessionResponse> {
  return apiRequest<AuthSessionResponse>("/api/app/auth/login", {
    method: "POST",
    body: JSON.stringify({
      user_id: userId,
      password,
      keep_logged_in: keepLoggedIn,
    }),
  });
}

export function identifyUser(userId: string): Promise<{ recognized: true }> {
  return apiRequest<{ recognized: true }>("/api/app/auth/identify", {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
}

export function forgotPassword(userId: string): Promise<{ message: string }> {
  return apiRequest<{ message: string }>("/api/app/auth/forgot-password", {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
}

export function refreshSession(
  refreshToken: string,
): Promise<AuthSessionResponse> {
  return apiRequest<AuthSessionResponse>("/api/app/auth/refresh", {
    method: "POST",
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
}

export function logout(accessToken: string): Promise<{ message: string }> {
  return apiRequest<{ message: string }>("/api/app/auth/logout", {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}
import { Platform } from "react-native";
