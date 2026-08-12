import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";
import { Redirect } from "expo-router";
import { useEffect, useState } from "react";
import { StyleSheet, Switch } from "react-native";

import { AppPressable as Pressable } from "@/components/AppPressable";
import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";
import { AppShell } from "@/components/AppShell";
import { useAppPreferences } from "@/context/AppPreferencesContext";
import { useAuth } from "@/context/AuthContext";
import type { AppPreferences } from "@/services/authApi";

const THEMES = [["light", "淺色"], ["dark", "深色"]] as const;
const FONT_SIZES = [["small", "小"], ["medium", "中"], ["large", "大"]] as const;

export default function PreferencesScreen() {
  const { status, updatePreferences, user } = useAuth();
  const { colors, fontScale } = useAppPreferences();
  const styles = createStyles(colors, fontScale);
  const [theme, setTheme] = useState<AppPreferences["theme_preference"]>(user?.theme_preference ?? "light");
  const [fontSize, setFontSize] = useState<AppPreferences["font_size_preference"]>(user?.font_size_preference ?? "medium");
  const [privacyMask, setPrivacyMask] = useState(user?.privacy_mask_enabled ?? false);
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!user) return;
    setTheme(user.theme_preference);
    setFontSize(user.font_size_preference);
    setPrivacyMask(user.privacy_mask_enabled);
  }, [user]);

  if (status === "guest") return <Redirect href="/login" />;

  const save = async () => {
    setSaving(true);
    setMessage(null);
    try {
      setMessage(await updatePreferences({
        theme_preference: theme,
        font_size_preference: fontSize,
        privacy_mask_enabled: privacyMask,
      }));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "設定儲存失敗，請稍後再試");
    } finally {
      setSaving(false);
    }
  };

  return (
    <AppShell title="APP 設定">
      <View style={styles.card}>
        <View style={styles.titleRow}>
          <MaterialCommunityIcons color={colors.primary} name="theme-light-dark" size={27} />
          <Text style={styles.title}>顯示模式</Text>
        </View>
        <Text style={styles.description}>選擇整個 APP 使用的畫面明暗。</Text>
        <View style={styles.options}>{THEMES.map(([value, label]) => <Pressable key={value} onPress={() => setTheme(value)} style={[styles.option, theme === value && styles.optionSelected]}><MaterialCommunityIcons color={theme === value ? colors.white : colors.primary} name={value === "dark" ? "weather-night" : "white-balance-sunny"} size={20} /><Text style={[styles.optionText, theme === value && styles.optionTextSelected]}>{label}</Text></Pressable>)}</View>
      </View>

      <View style={styles.card}>
        <View style={styles.titleRow}>
          <MaterialCommunityIcons color={colors.primary} name="format-size" size={27} />
          <Text style={styles.title}>字體大小</Text>
        </View>
        <Text style={styles.description}>選擇 APP 文字顯示大小。</Text>
        <View style={styles.options}>{FONT_SIZES.map(([value, label]) => <Pressable key={value} onPress={() => setFontSize(value)} style={[styles.option, fontSize === value && styles.optionSelected]}><Text style={[styles.optionText, fontSize === value && styles.optionTextSelected]}>{label}</Text></Pressable>)}</View>
      </View>

      <View style={styles.card}>
        <View style={styles.switchRow}>
          <View style={styles.switchCopy}>
            <View style={styles.titleRow}><MaterialCommunityIcons color={colors.primary} name="eye-lock-outline" size={27} /><Text style={styles.title}>隱私數字遮罩</Text></View>
            <Text style={styles.description}>遮蔽金額、薪資、體態數值與考試分數；點擊遮罩可暫時顯示。</Text>
          </View>
          <Switch onValueChange={setPrivacyMask} thumbColor={colors.white} trackColor={{ false: colors.border, true: colors.primary }} value={privacyMask} />
        </View>
      </View>

      {message ? <Text accessibilityLiveRegion="polite" style={styles.message}>{message}</Text> : null}
      <Pressable disabled={saving} onPress={() => void save()} style={[styles.saveButton, saving && styles.disabled]}><Text style={styles.saveText}>{saving ? "儲存中…" : "儲存設定"}</Text></Pressable>
    </AppShell>
  );
}

const createStyles = (colors: ReturnType<typeof useAppPreferences>["colors"], fontScale: number) => StyleSheet.create({
  card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 18, borderWidth: 1, gap: 12, padding: 20 },
  titleRow: { alignItems: "center", flexDirection: "row", gap: 10 },
  title: { color: colors.text, fontSize: 18 * fontScale, fontWeight: "900" },
  description: { color: colors.textMuted, fontSize: 13 * fontScale, lineHeight: 20 * fontScale },
  options: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  option: { alignItems: "center", backgroundColor: colors.primarySoft, borderColor: colors.border, borderRadius: 12, borderWidth: 1, flexDirection: "row", gap: 7, minWidth: 92, paddingHorizontal: 17, paddingVertical: 11 },
  optionSelected: { backgroundColor: colors.primary, borderColor: colors.primary },
  optionText: { color: colors.primaryDark, fontSize: 14 * fontScale, fontWeight: "800" },
  optionTextSelected: { color: colors.white },
  switchRow: { alignItems: "center", flexDirection: "row", gap: 16, justifyContent: "space-between" },
  switchCopy: { flex: 1, gap: 9 },
  message: { color: colors.primaryDark, fontSize: 14 * fontScale, fontWeight: "800", textAlign: "center" },
  saveButton: { alignItems: "center", alignSelf: "flex-start", backgroundColor: colors.primary, borderRadius: 12, minWidth: 150, paddingHorizontal: 22, paddingVertical: 13 },
  saveText: { color: colors.white, fontSize: 14 * fontScale, fontWeight: "900" },
  disabled: { opacity: 0.55 },
});
