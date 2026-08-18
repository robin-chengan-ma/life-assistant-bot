import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";
import { type Href, useRouter } from "expo-router";
import { type PropsWithChildren, type RefObject, useRef, useState } from "react";
import { Image, Modal, SafeAreaView, ScrollView, StyleSheet } from "react-native";

import { AppPressable as Pressable } from "@/components/AppPressable";
import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";
import { AppBackground } from "@/components/AppBackground";
import { colors } from "@/constants/theme";
import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import { useAppPreferences } from "@/context/AppPreferencesContext";
import type { AnalyticsModule } from "@/services/analyticsApi";

const MODULE_ICONS: Record<AnalyticsModule, keyof typeof MaterialCommunityIcons.glyphMap> = {
  todos: "calendar-check-outline",
  body: "heart-pulse",
  finance: "wallet-outline",
  mood: "emoticon-happy-outline",
  jobs: "briefcase-outline",
  exams: "certificate-outline",
  skills: "lightbulb-on-outline",
};
const COMMON_MODULES: AnalyticsModule[] = ["todos", "body", "finance", "mood"];
const OWNER_MODULES: AnalyticsModule[] = ["skills", "jobs", "exams"];
const LIFESTYLE_LINKS: Array<{ href: string; icon: keyof typeof MaterialCommunityIcons.glyphMap; label: string; color: string }> = [
  { href: "/collections", icon: "bookmark-multiple-outline", label: "收藏清單", color: "#D39719" },
  { href: "/exploration", icon: "map-marker-radius-outline", label: "探索地圖", color: "#278DA8" },
  { href: "/achievements", icon: "trophy-outline", label: "成果展示", color: "#A56CC1" },
];

export function AppShell({ children, scrollViewRef, title }: PropsWithChildren<{ scrollViewRef?: RefObject<ScrollView | null>; title: string }>) {
  const router = useRouter();
  const { user, logout } = useAuth();
  const { data } = useDashboard();
  const { colors } = useAppPreferences();
  const styles = createStyles(colors);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [logoutConfirmOpen, setLogoutConfirmOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = (message: string) => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToast(message);
    toastTimer.current = setTimeout(() => setToast(null), 2400);
  };

  const openModule = (module: AnalyticsModule, isEnabled: boolean) => {
    if (!isEnabled) {
      showToast("請先把功能打開才能使用喔");
      return;
    }
    setDrawerOpen(false);
    router.push(`/analytics/${module}` as Href);
  };

  const formatLoginTime = (value: string | null | undefined) => {
    if (!value) return "尚無紀錄";
    return new Date(value).toLocaleString("sv-SE", {
      hour12: false,
      timeZone: "Asia/Taipei",
    });
  };

  const confirmLogout = () => {
    setProfileOpen(false);
    setLogoutConfirmOpen(true);
  };

  const executeLogout = async () => {
    setLogoutConfirmOpen(false);
    await logout();
    router.replace("/login");
  };

  return (
    <AppBackground>
      <SafeAreaView style={styles.page}>
      <View style={styles.header}>
        <Pressable accessibilityLabel="開啟選單" onPress={() => setDrawerOpen(true)} style={styles.headerButton}>
          <MaterialCommunityIcons color={colors.primaryDark} name="menu" size={28} />
        </Pressable>
        <Text numberOfLines={1} style={styles.headerTitle}>{title}</Text>
        <Pressable accessibilityLabel="開啟個人選單" onPress={() => setProfileOpen((value) => !value)}>
          <Image
            source={user?.gender === "female" ? require("../../assets/woman.png") : require("../../assets/boy.png")}
            style={styles.avatar}
          />
        </Pressable>
      </View>

      {profileOpen ? (
        <View style={styles.profileLayer}>
          <Pressable accessibilityLabel="關閉個人選單" onPress={() => setProfileOpen(false)} style={styles.profileBackdrop} />
          <View style={styles.profileMenu}>
          <View style={styles.profileGreeting}>
            <Image source={require("../../assets/wave.png")} style={styles.waveIcon} />
            <Text style={styles.profileRole}>嗨，{user?.role}</Text>
          </View>
          <Text style={styles.loginTime}>上次登入時間：{formatLoginTime(user?.previous_login_at)}</Text>
          <Text style={styles.loginTime}>最近登入時間：{formatLoginTime(user?.current_login_at)}</Text>
          <Pressable onPress={() => { setProfileOpen(false); router.push("/settings/profile"); }} style={styles.profileMenuButton}>
            <MaterialCommunityIcons color={colors.primary} name="account-details-outline" size={22} />
            <Text style={styles.profileMenuButtonText}>個人基本資訊</Text>
          </Pressable>
          <Pressable onPress={() => { setProfileOpen(false); router.push("/settings/important-days"); }} style={styles.profileMenuButton}>
            <MaterialCommunityIcons color={colors.primary} name="calendar-star" size={22} />
            <Text style={styles.profileMenuButtonText}>重要日子設定</Text>
          </Pressable>
          <Pressable onPress={() => { setProfileOpen(false); router.push("/settings/preferences"); }} style={styles.profileMenuButton}>
            <MaterialCommunityIcons color={colors.primary} name="cog-outline" size={22} />
            <Text style={styles.profileMenuButtonText}>APP 設定</Text>
          </Pressable>
          <Pressable onPress={confirmLogout} style={styles.logoutButton}><Text style={styles.logoutText}>登出</Text></Pressable>
          </View>
        </View>
      ) : null}

      <ScrollView contentContainerStyle={styles.content} ref={scrollViewRef}>{children}</ScrollView>

      <Modal animationType="fade" onRequestClose={() => setDrawerOpen(false)} transparent visible={drawerOpen}>
        <View style={styles.modalRoot}>
          <Pressable onPress={() => setDrawerOpen(false)} style={styles.backdrop} />
          <View style={styles.drawer}>
            <View style={styles.drawerBrand}><Image source={require("../../assets/Robinson.png")} style={styles.drawerLogo} /><Text style={styles.drawerTitle}>羅賓森</Text></View>
            <Pressable onPress={() => { setDrawerOpen(false); router.replace("/home"); }} style={styles.drawerItem}>
              <MaterialCommunityIcons color={colors.primary} name="view-dashboard-outline" size={22} /><Text style={styles.drawerText}>首頁</Text>
            </Pressable>
            {COMMON_MODULES.map((key) => { const item = data?.navigation[key]; return item ? (
              <Pressable key={key} onPress={() => openModule(key, item.is_enabled)} style={[styles.drawerItem, !item.is_enabled && styles.drawerItemDisabled]}>
                <MaterialCommunityIcons color={item.is_enabled ? item.color : colors.textMuted} name={MODULE_ICONS[key]} size={22} />
                <Text style={[styles.drawerText, !item.is_enabled && styles.disabledText]}>{item.label}</Text>
              </Pressable>
            ) : null; })}
            {LIFESTYLE_LINKS.map((item) => <Pressable key={item.label} onPress={() => { setDrawerOpen(false); router.push(item.href as Href); }} style={styles.drawerItem}><MaterialCommunityIcons color={item.color} name={item.icon} size={22} /><Text style={styles.drawerText}>{item.label}</Text></Pressable>)}
            {OWNER_MODULES.map((key) => { const item = data?.navigation[key]; return item ? (
              <Pressable key={key} onPress={() => openModule(key, item.is_enabled)} style={[styles.drawerItem, !item.is_enabled && styles.drawerItemDisabled]}>
                <MaterialCommunityIcons color={item.is_enabled ? item.color : colors.textMuted} name={MODULE_ICONS[key]} size={22} />
                <Text style={[styles.drawerText, !item.is_enabled && styles.disabledText]}>{item.label}</Text>
              </Pressable>
            ) : null; })}
          </View>
        </View>
      </Modal>

      <Modal animationType="fade" onRequestClose={() => setLogoutConfirmOpen(false)} transparent visible={logoutConfirmOpen}>
        <View style={styles.confirmRoot}>
          <Pressable onPress={() => setLogoutConfirmOpen(false)} style={styles.confirmBackdrop} />
          <View style={styles.confirmCard}>
            <View style={styles.confirmHeading}>
              <Image source={require("../../assets/logout.png")} style={styles.logoutIcon} />
              <Text style={styles.confirmTitle}>確認登出？</Text>
            </View>
            <Text style={styles.confirmMessage}>確定要登出羅賓森嗎？</Text>
            <View style={styles.confirmActions}>
              <Pressable onPress={() => setLogoutConfirmOpen(false)} style={styles.confirmCancel}><Text style={styles.confirmCancelText}>取消</Text></Pressable>
              <Pressable onPress={() => void executeLogout()} style={styles.confirmLogout}><Text style={styles.confirmLogoutText}>登出</Text></Pressable>
            </View>
          </View>
        </View>
      </Modal>

      {toast ? <View accessibilityLiveRegion="polite" style={styles.toast}><Text style={styles.toastText}>{toast}</Text></View> : null}
      </SafeAreaView>
    </AppBackground>
  );
}

const createStyles = (colors: ReturnType<typeof useAppPreferences>["colors"]) => StyleSheet.create({
  page: { backgroundColor: "transparent", flex: 1 },
  header: { alignItems: "center", backgroundColor: colors.surface, borderBottomColor: colors.border, borderBottomWidth: 1, flexDirection: "row", justifyContent: "space-between", paddingHorizontal: 16, paddingVertical: 10, zIndex: 3 },
  headerButton: { padding: 5 },
  headerTitle: { color: colors.text, flex: 1, fontSize: 18, fontWeight: "800", marginHorizontal: 12, textAlign: "left" },
  avatar: { backgroundColor: colors.primarySoft, borderColor: colors.primary, borderRadius: 21, borderWidth: 1, height: 42, width: 42 },
  content: { alignSelf: "center", gap: 16, maxWidth: 980, padding: 18, width: "100%" },
  profileLayer: { bottom: 0, left: 0, position: "absolute", right: 0, top: 0, zIndex: 5 },
  profileBackdrop: { bottom: 0, left: 0, position: "absolute", right: 0, top: 0 },
  profileMenu: { alignItems: "flex-start", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 14, borderWidth: 1, elevation: 8, gap: 7, padding: 14, position: "absolute", right: 14, shadowColor: "#143C36", shadowOffset: { width: 0, height: 5 }, shadowOpacity: 0.12, shadowRadius: 12, top: 64, width: 270 },
  profileRole: { color: colors.text, fontSize: 15, fontWeight: "800" },
  profileGreeting: { alignItems: "center", flexDirection: "row", gap: 8 },
  waveIcon: { height: 26, width: 26 },
  loginTime: { color: colors.textMuted, fontSize: 12, lineHeight: 18 },
  profileMenuButton: { alignItems: "center", borderRadius: 11, flexDirection: "row", gap: 13, paddingVertical: 8, width: "100%" },
  profileMenuButtonText: { color: colors.text, fontSize: 15, fontWeight: "700" },
  logoutButton: { alignItems: "center", backgroundColor: colors.primarySoft, borderRadius: 9, marginTop: 8, padding: 9, width: "100%" },
  logoutText: { color: colors.primaryDark, fontWeight: "800" },
  modalRoot: { flex: 1, flexDirection: "row" },
  backdrop: { backgroundColor: "rgba(18, 35, 32, 0.38)", bottom: 0, left: 0, position: "absolute", right: 0, top: 0 },
  drawer: { backgroundColor: colors.surface, elevation: 12, gap: 5, maxWidth: 310, paddingHorizontal: 16, paddingTop: 55, shadowColor: "#000", shadowOpacity: 0.18, shadowRadius: 18, width: "82%" },
  drawerBrand: { alignItems: "center", borderBottomColor: colors.border, borderBottomWidth: 1, flexDirection: "row", gap: 12, marginBottom: 12, paddingBottom: 18 },
  drawerLogo: { borderRadius: 24, height: 48, width: 48 },
  drawerTitle: { color: colors.primaryDark, fontSize: 22, fontWeight: "900" },
  drawerItem: { alignItems: "center", borderRadius: 11, flexDirection: "row", gap: 13, paddingHorizontal: 12, paddingVertical: 12 },
  drawerItemDisabled: { backgroundColor: "#EEF0EF" },
  drawerText: { color: colors.text, fontSize: 15, fontWeight: "700" },
  disabledText: { color: colors.textMuted },
  toast: { alignSelf: "center", backgroundColor: "rgba(32,45,43,0.94)", borderRadius: 22, bottom: 30, paddingHorizontal: 20, paddingVertical: 12, position: "absolute", zIndex: 20 },
  toastText: { color: colors.white, fontSize: 14, fontWeight: "700" },
  confirmRoot: { alignItems: "center", flex: 1, justifyContent: "center", padding: 24 },
  confirmBackdrop: { backgroundColor: "rgba(18, 35, 32, 0.48)", bottom: 0, left: 0, position: "absolute", right: 0, top: 0 },
  confirmCard: { backgroundColor: colors.surface, borderRadius: 20, elevation: 12, gap: 10, maxWidth: 390, padding: 22, width: "100%" },
  confirmHeading: { alignItems: "center", flexDirection: "row", gap: 10 },
  confirmTitle: { color: colors.text, fontSize: 20, fontWeight: "900" },
  logoutIcon: { height: 34, width: 34 },
  confirmMessage: { color: colors.textMuted, fontSize: 14, lineHeight: 21 },
  confirmActions: { flexDirection: "row", gap: 10, justifyContent: "flex-end", marginTop: 8 },
  confirmCancel: { borderColor: colors.border, borderRadius: 10, borderWidth: 1, paddingHorizontal: 18, paddingVertical: 10 },
  confirmCancelText: { color: colors.textMuted, fontWeight: "800" },
  confirmLogout: { backgroundColor: colors.danger, borderRadius: 10, paddingHorizontal: 18, paddingVertical: 10 },
  confirmLogoutText: { color: colors.white, fontWeight: "800" },
});
