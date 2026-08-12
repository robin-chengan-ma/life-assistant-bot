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
    output: "single",
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
