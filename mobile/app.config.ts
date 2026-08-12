import type { ExpoConfig } from "expo/config";

const config: ExpoConfig = {
  name: "羅賓森",
  slug: "robinson-mobile",
  version: "0.1.0",
  orientation: "portrait",
  icon: "./assets/Robinson.png",
  scheme: "robinson",
  userInterfaceStyle: "automatic",
  ios: {
    bundleIdentifier: "com.robinma.robinson",
    config: {
      usesNonExemptEncryption: false,
    },
    supportsTablet: true,
  },
  android: {
    adaptiveIcon: {
      foregroundImage: "./assets/Robinson.png",
      backgroundColor: "#E8F5F1",
    },
    package: "com.robinma.robinson",
  },
  web: {
    bundler: "metro",
    // 2026-08-12 修正：改為 "static"，因為 `app/+html.tsx`（自訂 <head> 的 App icon、
    // manifest、viewport 設定）只有在 "static" 輸出模式下才會被套用；先前用 "single"
    // 時，實測發現 +html.tsx 完全沒有生效，正式部署的 HTML 仍是 Expo 預設樣板。
    output: "static",
    favicon: "./assets/Robinson.png",
  },
  plugins: [
    "expo-router",
    [
      "expo-secure-store",
      {
        configureAndroidBackup: true,
        faceIDPermission: "允許羅賓森安全存取登入資訊。",
      },
    ],
    [
      "expo-image-picker",
      {
        cameraPermission: "允許羅賓森使用相機拍攝今日飲食。",
        photosPermission: "允許羅賓森讀取你選擇的飲食照片。",
      },
    ],
  ],
  experiments: {
    typedRoutes: true,
  },
};

export default config;
