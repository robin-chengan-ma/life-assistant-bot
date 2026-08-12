import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";
import { Redirect } from "expo-router";
import { StyleSheet } from "react-native";

import { AppShell } from "@/components/AppShell";
import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";
import { useAppPreferences } from "@/context/AppPreferencesContext";
import { useAuth } from "@/context/AuthContext";

export default function AchievementsScreen() {
  const { status } = useAuth();
  const { colors } = useAppPreferences();
  const styles = createStyles(colors);
  if (status === "guest") return <Redirect href="/login" />;
  return <AppShell title="成果展示"><View style={styles.card}><MaterialCommunityIcons color="#A56CC1" name="trophy-outline" size={40} /><Text style={styles.title}>成果展示</Text><Text style={styles.description}>這裡將以卡片顯示已完成的目標與個人成就。目前尚無成果紀錄。</Text></View></AppShell>;
}

const createStyles = (colors: ReturnType<typeof useAppPreferences>["colors"]) => StyleSheet.create({ card: { alignItems: "center", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 18, borderWidth: 1, gap: 10, padding: 30 }, title: { color: colors.text, fontSize: 22, fontWeight: "900" }, description: { color: colors.textMuted, fontSize: 14, lineHeight: 22, maxWidth: 560, textAlign: "center" } });
