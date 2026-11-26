import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";
import { Redirect, type Href, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Alert, StyleSheet } from "react-native";

import { AppPressable as Pressable } from "@/components/AppPressable";
import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";
import { AppShell } from "@/components/AppShell";
import { defaultDateRange } from "@/components/DateRangeFilter";
import { HomeCalendar } from "@/components/HomeCalendar";
import { RecordModal } from "@/components/RecordModal";
import { SensitiveValue } from "@/components/SensitiveValue";
import { useAppPreferences } from "@/context/AppPreferencesContext";
import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import {
  getAnalytics,
  type AnalyticsModule,
  type BodyAnalytics,
  type RecordItem,
  type RecordKind,
} from "@/services/analyticsApi";

export default function HomeScreen() {
  const router = useRouter();
  const { status, authorizedRequest } = useAuth();
  const { data, error, isLoading, reload } = useDashboard();
  const { colors, theme } = useAppPreferences();
  const styles = createStyles(colors, theme);
  const [body, setBody] = useState<BodyAnalytics | null>(null);
  const [recordTarget, setRecordTarget] = useState<{ kind: RecordKind; initial: RecordItem | null; defaults?: Partial<RecordItem> | null } | null>(null);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  const loadPreviews = useCallback(async () => {
    if (status !== "authenticated") return;
    const range = defaultDateRange();
    const bodyData = await getAnalytics(authorizedRequest, "body", range).catch(() => null);
    setBody(bodyData);
  }, [authorizedRequest, status]);
  useEffect(() => { void loadPreviews(); }, [loadPreviews]);

  if (status === "guest") return <Redirect href="/login" />;

  const openModule = (module: AnalyticsModule) => {
    const item = data?.navigation[module];
    if (item && !item.is_enabled) {
      Alert.alert("提醒", "請先把功能打開才能使用喔");
      return;
    }
    router.push(`/analytics/${module}` as Href);
  };

  const summary = data?.summary;
  const today = data?.date;
  const latestTodayRecord = (kind: RecordKind): RecordItem | null => {
    if (!today) return null;
    if (kind === "diet") return body?.diet_records.find((item) => item.entry_date === today) ?? null;
    if (kind === "weight") return body?.latest_body_record?.entry_date === today ? body.latest_body_record : null;
    return null;
  };
  const cards: Array<{ module: AnalyticsModule; kind: RecordKind; title: string; text: React.ReactNode; icon: keyof typeof MaterialCommunityIcons.glyphMap; count: number }> = [
    { module: "finance", kind: "finance", title: "記帳分析", text: <View><View style={styles.inlineText}><Text style={styles.cardText}>收入：{summary?.income_count ? `今日已記 ${summary.income_count} 筆，共 ` : "無紀錄"}</Text>{summary?.income_count ? <SensitiveValue style={styles.cardText}>{`${Number(summary.income_today).toLocaleString()} 元`}</SensitiveValue> : null}</View><View style={styles.inlineText}><Text style={styles.cardText}>支出：{summary?.expense_count ? `今日已記 ${summary.expense_count} 筆，共 ` : "無紀錄"}</Text>{summary?.expense_count ? <SensitiveValue style={styles.cardText}>{`${Number(summary.expense_today).toLocaleString()} 元`}</SensitiveValue> : null}</View></View>, icon: "wallet-outline", count: Number(summary?.income_count ?? 0) + Number(summary?.expense_count ?? 0) },
    { module: "body", kind: "diet", title: "飲食紀錄", text: summary?.diet_count ? `今日已記 ${summary.diet_count} 筆，大約吸收 ${Number(summary.diet_calories ?? 0).toLocaleString()} 大卡` : "今日尚未記錄飲食", icon: "food-apple-outline", count: Number(summary?.diet_count ?? 0) },
    { module: "body", kind: "exercise", title: "運動紀錄", text: summary?.exercise_count ? `今日已記 ${summary.exercise_count} 筆，大約消耗 ${Number(summary.exercise_calories ?? 0).toLocaleString()} 大卡` : "今日尚未記錄運動", icon: "run", count: Number(summary?.exercise_count ?? 0) },
    { module: "body", kind: "weight", title: "體態紀錄", text: summary?.latest_weight ? <View style={styles.inlineText}><Text style={styles.cardText}>目前體重為 </Text><SensitiveValue style={styles.cardText}>{`${summary.latest_weight} 公斤`}</SensitiveValue></View> : "尚未紀錄過體重", icon: "scale-bathroom", count: Number(summary?.weight_count ?? 0) },
  ];

  return (
    <>
      <AppShell title="首頁">
      {isLoading && !data ? <ActivityIndicator color={colors.primary} size="large" /> : null}
      {error ? <Pressable onPress={() => void reload()} style={styles.errorCard}><Text style={styles.errorText}>{error}</Text><Text style={styles.retry}>點此重新載入</Text></Pressable> : null}

      <HomeCalendar />

      <View style={styles.cardGrid}>
        <Pressable onPress={() => router.push("/todo")} style={styles.summaryCard}><MaterialCommunityIcons color="#3B82F6" name="calendar-check-outline" size={27} /><View style={styles.flex}><View style={styles.cardTitleRow}><Text style={styles.cardTitle}>待辦事項</Text><Pressable onPress={(event) => { event.stopPropagation(); router.push("/todo"); }} style={styles.measureButton}><MaterialCommunityIcons color={theme === "dark" ? colors.background : colors.white} name="calendar-plus" size={17} /><Text style={styles.measureButtonText}>新增待辦</Text></Pressable></View><Text style={styles.cardText}>今日有 {summary?.todo_count ?? 0} 件待辦事項</Text></View></Pressable>
        {cards.map((card, index) => { const item = data?.navigation[card.module]; const disabled = item ? !item.is_enabled : false; const singleDaily = (["diet", "weight"] as RecordKind[]).includes(card.kind); const initial = singleDaily ? latestTodayRecord(card.kind) : null; const defaults = card.kind === "weight" ? body?.body_defaults ?? null : null; const updating = Boolean(initial); return <Pressable key={`${card.title}-${index}`} onPress={() => openModule(card.module)} style={[styles.summaryCard, disabled && styles.disabledCard]}><MaterialCommunityIcons color={disabled ? colors.textMuted : item?.color ?? colors.primary} name={card.icon} size={27} /><View style={styles.flex}><View style={styles.cardTitleRow}><Text style={[styles.cardTitle, disabled && styles.disabledText]}>{card.title}</Text><Pressable disabled={disabled} onPress={(event) => { event.stopPropagation(); setRecordTarget({ kind: card.kind, initial, defaults }); }} style={[styles.measureButton, updating && styles.updateButton, disabled && styles.measureButtonDisabled]}><MaterialCommunityIcons color={theme === "dark" ? colors.background : colors.white} name="pencil-outline" size={17} /><Text style={styles.measureButtonText}>{updating ? "更新紀錄" : card.count > 0 && !singleDaily ? "再記一筆" : "記錄一下"}</Text></Pressable></View><View style={styles.cardTextRow}>{typeof card.text === "string" ? <Text style={styles.cardText}>{card.text}</Text> : card.text}</View></View></Pressable>; })}
      </View>
      </AppShell>

      {savedMessage ? <View accessibilityLiveRegion="polite" style={styles.savedToast}><Text style={styles.savedToastText}>{savedMessage}</Text></View> : null}

      {recordTarget ? <RecordModal authorizedRequest={authorizedRequest} defaults={recordTarget.defaults} initial={recordTarget.initial} kind={recordTarget.kind} onClose={() => setRecordTarget(null)} onSaved={async () => { await Promise.all([reload(), loadPreviews()]); setSavedMessage(recordTarget.initial ? "紀錄已更新" : "紀錄已儲存"); setTimeout(() => setSavedMessage(null), 2400); }} visible /> : null}
    </>
  );
}

const createStyles = (colors: ReturnType<typeof useAppPreferences>["colors"], theme: ReturnType<typeof useAppPreferences>["theme"]) => StyleSheet.create({
  cardGrid: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  summaryCard: { alignItems: "flex-start", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 17, borderWidth: 1, flexDirection: "row", gap: 13, minWidth: 260, padding: 17, flexGrow: 1, flexBasis: "46%" },
  disabledCard: { backgroundColor: "#E8EBEA", opacity: 0.8 },
  disabledText: { color: colors.textMuted },
  flex: { flex: 1 },
  cardTitleRow: { alignItems: "center", flexDirection: "row", gap: 10, justifyContent: "space-between" },
  cardTitle: { color: colors.text, fontSize: 15, fontWeight: "800" },
  cardText: { color: colors.textMuted, fontSize: 13, lineHeight: 19, marginTop: 4 },
  inlineText: { alignItems: "baseline", flexDirection: "row", flexWrap: "wrap" },
  cardTextRow: { alignItems: "center", flexDirection: "row", gap: 8 },
  errorCard: { backgroundColor: "#FFF0F0", borderRadius: 14, gap: 4, padding: 16 },
  errorText: { color: "#A33D3D", fontSize: 13 },
  retry: { color: colors.primary, fontSize: 12, fontWeight: "800" },
  measureButton: { alignItems: "center", backgroundColor: colors.primary, borderRadius: 10, flexDirection: "row", gap: 6, paddingHorizontal: 13, paddingVertical: 9 },
  updateButton: { backgroundColor: "#3B82F6" },
  measureButtonDisabled: { opacity: 0.55 },
  measureButtonText: { color: colors.white, fontSize: 12, fontWeight: "800" },
  savedToast: { alignSelf: "center", backgroundColor: colors.primaryDark, borderRadius: 20, bottom: 22, paddingHorizontal: 18, paddingVertical: 10, position: "absolute", zIndex: 20 },
  savedToastText: { color: colors.white, fontWeight: "800" },
});
