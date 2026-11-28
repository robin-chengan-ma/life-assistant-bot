import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useEffect, useState } from "react";
import { Image, Modal, Platform, StyleSheet } from "react-native";

import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";

import { AuthProvider, useAuth } from "@/context/AuthContext";
import { AppPreferencesProvider, useAppPreferences } from "@/context/AppPreferencesContext";
import { DashboardProvider } from "@/context/DashboardContext";

// 2026-11-28（見 docs/ADR/debug/mobile-app.md）：Robin 回報從登入頁導頁到首頁的那一瞬間，畫面
// 會可以被用力左右滑動、版面跟著位移，研判是 Stack 預設的橫向滑動切換動畫，切換過程中舊畫面被
// `transform: translateX` 推到螢幕外時，瀏覽器仍把它算進文件的可橫向捲動範圍，切完後沒有收回來。
// Web／PWA 版本直接關閉切換動畫（原生 App 不受影響，維持原本手感）。
const WEB_SCREEN_ANIMATION = Platform.OS === "web" ? "none" : undefined;

export default function RootLayout() {
  return (
    <AuthProvider>
      <AppPreferencesProvider>
        <DashboardProvider>
          <ThemedApp />
        </DashboardProvider>
      </AppPreferencesProvider>
    </AuthProvider>
  );
}

function ThemedApp() {
  const { theme } = useAppPreferences();
  return <><StatusBar style={theme === "dark" ? "light" : "dark"} /><Stack screenOptions={{ headerShown: false, animation: WEB_SCREEN_ANIMATION }} /><LoginSuccessNotice /></>;
}

function LoginSuccessNotice() {
  const { clearLoginNotice, loginNotice } = useAuth();
  const [visibleMessage, setVisibleMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!loginNotice) return undefined;
    setVisibleMessage(loginNotice);
    const timer = setTimeout(() => {
      setVisibleMessage(null);
      clearLoginNotice();
    }, 1000);
    return () => clearTimeout(timer);
  }, [clearLoginNotice, loginNotice]);

  return (
    <Modal animationType="fade" transparent visible={Boolean(visibleMessage)}>
      <View pointerEvents="none" style={styles.noticeBackdrop}>
        <View style={styles.noticeCard}>
          <Image source={require("../assets/check.png")} style={styles.noticeIcon} />
          <Text style={styles.noticeText}>{visibleMessage}</Text>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  noticeBackdrop: {
    alignItems: "center",
    backgroundColor: "rgba(18, 35, 32, 0.25)",
    flex: 1,
    justifyContent: "center",
    padding: 24,
    width: "100%",
  },
  noticeCard: {
    alignItems: "center",
    backgroundColor: "#FFFFFF",
    borderRadius: 18,
    elevation: 10,
    flexDirection: "row",
    gap: 12,
    maxWidth: 420,
    paddingHorizontal: 26,
    paddingVertical: 22,
    shadowColor: "#143C36",
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.18,
    shadowRadius: 18,
    width: "100%",
  },
  noticeText: {
    color: "#0E5E55",
    flex: 1,
    fontSize: 17,
    fontWeight: "800",
    lineHeight: 25,
    textAlign: "center",
  },
  noticeIcon: { height: 38, width: 38 },
});
