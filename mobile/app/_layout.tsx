import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useEffect, useState } from "react";
import { Image, Modal, StyleSheet } from "react-native";

import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";

import { AuthProvider, useAuth } from "@/context/AuthContext";
import { AppPreferencesProvider, useAppPreferences } from "@/context/AppPreferencesContext";
import { DashboardProvider } from "@/context/DashboardContext";

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
  return <><StatusBar style={theme === "dark" ? "light" : "dark"} /><Stack screenOptions={{ headerShown: false }} /><LoginSuccessNotice /></>;
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
