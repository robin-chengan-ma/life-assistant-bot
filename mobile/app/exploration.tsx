import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";
import { Redirect } from "expo-router";
import { StyleSheet } from "react-native";

import { AppShell } from "@/components/AppShell";
import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";
import { useAppPreferences } from "@/context/AppPreferencesContext";
import { useAuth } from "@/context/AuthContext";

export default function ExplorationScreen() {
  const { status } = useAuth();
  const { colors } = useAppPreferences();
  const styles = createStyles(colors);
  if (status === "guest") return <Redirect href="/login" />;
  return <AppShell title="探索地圖"><View style={styles.card}><MaterialCommunityIcons color="#278DA8" name="map-marker-radius-outline" size={40} /><Text style={styles.title}>探索地圖</Text><Text style={styles.description}>地圖顯示元件已完成相容性驗證；待探索事件 API 接上後，將在此依國家與縣市篩選旅遊、餐廳、山岳與景點紀錄。</Text></View></AppShell>;
}

const createStyles = (colors: ReturnType<typeof useAppPreferences>["colors"]) => StyleSheet.create({ card: { alignItems: "center", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 18, borderWidth: 1, gap: 10, padding: 30 }, title: { color: colors.text, fontSize: 22, fontWeight: "900" }, description: { color: colors.textMuted, fontSize: 14, lineHeight: 22, maxWidth: 560, textAlign: "center" } });
