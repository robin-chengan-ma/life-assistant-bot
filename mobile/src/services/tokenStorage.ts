import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

const REFRESH_TOKEN_KEY = "robinson_refresh_token";

function webStorageAvailable(): boolean {
  return Platform.OS === "web" && typeof window !== "undefined";
}

export async function getRefreshToken(): Promise<string | null> {
  // Expo Web 本機預覽沒有原生 Keychain；此 fallback 不會用於 iOS／Android 正式 App。
  if (webStorageAvailable()) {
    return window.localStorage.getItem(REFRESH_TOKEN_KEY);
  }
  return SecureStore.getItemAsync(REFRESH_TOKEN_KEY);
}

export async function saveRefreshToken(refreshToken: string): Promise<void> {
  if (webStorageAvailable()) {
    window.localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
    return;
  }
  await SecureStore.setItemAsync(REFRESH_TOKEN_KEY, refreshToken, {
    keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  });
}

export async function clearRefreshToken(): Promise<void> {
  if (webStorageAvailable()) {
    window.localStorage.removeItem(REFRESH_TOKEN_KEY);
    return;
  }
  await SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY);
}
