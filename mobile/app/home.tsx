import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";
import { Redirect, type Href, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Alert, StyleSheet } from "react-native";

import { AppPressable as Pressable } from "@/components/AppPressable";
import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";
import { AppShell } from "@/components/AppShell";
import { CollectionModal } from "@/components/CollectionModal";
import { defaultDateRange } from "@/components/DateRangeFilter";
import { RecordModal } from "@/components/RecordModal";
import { SensitiveValue } from "@/components/SensitiveValue";
import { useAppPreferences } from "@/context/AppPreferencesContext";
import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import {
  getAnalytics,
  type AnalyticsModule,
  type BodyAnalytics,
  type MoodAnalytics,
  type RecordItem,
  type RecordKind,
} from "@/services/analyticsApi";
import { getCollectionItems, type CollectionResponse } from "@/services/collectionApi";
import { getAchievements, type AchievementResponse } from "@/services/lifeExplorationApi";

export default function HomeScreen() {
  const router = useRouter();
  const { status, authorizedRequest } = useAuth();
  const { data, error, isLoading, reload } = useDashboard();
  const { colors, theme } = useAppPreferences();
  const styles = createStyles(colors, theme);
  const [body, setBody] = useState<BodyAnalytics | null>(null);
  const [mood, setMood] = useState<MoodAnalytics | null>(null);
  const [collections, setCollections] = useState<CollectionResponse | null>(null);
  const [achievements, setAchievements] = useState<AchievementResponse | null>(null);
  const [collectionModalOpen, setCollectionModalOpen] = useState(false);
  const [recordTarget, setRecordTarget] = useState<{ kind: RecordKind; initial: RecordItem | null; defaults?: Partial<RecordItem> | null } | null>(null);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  const loadPreviews = useCallback(async () => {
    if (status !== "authenticated") return;
    const range = defaultDateRange();
    const [bodyData, moodData, collectionData, achievementData] = await Promise.all([
      getAnalytics(authorizedRequest, "body", range).catch(() => null),
      getAnalytics(authorizedRequest, "mood", range).catch(() => null),
      getCollectionItems(authorizedRequest).catch(() => null),
      getAchievements(authorizedRequest).catch(() => null),
    ]);
    setBody(bodyData); setMood(moodData); setCollections(collectionData); setAchievements(achievementData);
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
    if (kind === "mood") return mood?.items.slice().reverse().find((item) => item.date === today) as RecordItem ?? null;
    return null;
  };
  const moodEmoji = ({ happy_excited: "🥳", calm_relaxed: "😌", neutral: "🙂", tired_burned_out: "🫠", sad_down: "😢", angry_anxious: "😡" } as const)[summary?.latest_mood_category ?? ""] ?? "🙂";
  const cards: Array<{ module: AnalyticsModule; kind: RecordKind; title: string; text: React.ReactNode; icon: keyof typeof MaterialCommunityIcons.glyphMap; count: number }> = [
    { module: "todos", kind: "todo", title: "待辦事項", text: `今日有 ${summary?.todo_count ?? 0} 件待辦事項`, icon: "calendar-check-outline", count: Number(summary?.todo_count ?? 0) },
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

      <Pressable onPress={() => router.push("/settings/important-days")} style={styles.notificationCard}>
        <MaterialCommunityIcons color={colors.accent} name="bell-ring-outline" size={24} />
        <View style={styles.flex}><Text style={styles.cardTitle}>重要通知</Text>{data?.important_days?.length ? data.important_days.map((message, index) => <Text key={`${message}-${index}`} style={styles.cardText}>{message}</Text>) : <Text style={styles.cardText}>目前沒有重要日子</Text>}</View>
        <MaterialCommunityIcons color={colors.textMuted} name="chevron-right" size={22} />
      </Pressable>

      <View style={styles.cardGrid}>{cards.map((card, index) => { const item = data?.navigation[card.module]; const disabled = item ? !item.is_enabled : false; const singleDaily = (["diet", "weight", "mood"] as RecordKind[]).includes(card.kind); const initial = singleDaily ? latestTodayRecord(card.kind) : null; const defaults = card.kind === "weight" ? body?.body_defaults ?? null : null; const updating = Boolean(initial); return <Pressable key={`${card.title}-${index}`} onPress={() => openModule(card.module)} style={[styles.summaryCard, disabled && styles.disabledCard]}><MaterialCommunityIcons color={disabled ? colors.textMuted : item?.color ?? colors.primary} name={card.icon} size={27} /><View style={styles.flex}><View style={styles.cardTitleRow}><Text style={[styles.cardTitle, disabled && styles.disabledText]}>{card.title}</Text><Pressable disabled={disabled} onPress={(event) => { event.stopPropagation(); setRecordTarget({ kind: card.kind, initial, defaults }); }} style={[styles.measureButton, updating && styles.updateButton, disabled && styles.measureButtonDisabled]}><MaterialCommunityIcons color={theme === "dark" ? colors.background : colors.white} name={card.kind === "todo" ? "calendar-plus" : "pencil-outline"} size={17} /><Text style={styles.measureButtonText}>{card.kind === "todo" ? "新增待辦" : updating ? "更新紀錄" : card.count > 0 && !singleDaily ? "再記一筆" : "記錄一下"}</Text></Pressable></View><View style={styles.cardTextRow}>{typeof card.text === "string" ? <Text style={styles.cardText}>{card.text}</Text> : card.text}</View></View></Pressable>; })}
        <Pressable onPress={() => router.push("/achievements" as Href)} style={styles.summaryCard}><MaterialCommunityIcons color="#A56CC1" name="trophy-outline" size={27} /><View style={styles.flex}><View style={styles.cardTitleRow}><Text style={styles.cardTitle}>成果展示</Text><Pressable onPress={(event) => { event.stopPropagation(); router.push("/achievements" as Href); }} style={styles.measureButton}><MaterialCommunityIcons color={theme === "dark" ? colors.background : colors.white} name="plus" size={17} /><Text style={styles.measureButtonText}>新增成果</Text></Pressable></View><Text style={styles.cardText}>{achievements?.candidates.length ? `有 ${achievements.candidates.length} 項成果候選待你確認` : `已收藏 ${achievements?.achievements.length ?? 0} 項成果`}</Text></View></Pressable>
      </View>

      <View style={styles.cardGrid}>
        <Pressable onPress={() => router.push("/collections" as Href)} style={styles.summaryCard}><MaterialCommunityIcons color="#D39719" name="bookmark-multiple-outline" size={27} /><View style={styles.flex}><View style={styles.cardTitleRow}><Text style={styles.cardTitle}>收藏清單</Text><Pressable onPress={(event) => { event.stopPropagation(); setCollectionModalOpen(true); }} style={styles.measureButton}><MaterialCommunityIcons color={theme === "dark" ? colors.background : colors.white} name="plus" size={17} /><Text style={styles.measureButtonText}>新增收藏</Text></Pressable></View><Text style={styles.cardText}>目前收藏 {collections?.summary.total ?? 0} 筆，已造訪 {collections?.summary.visited ?? 0} 筆</Text></View></Pressable>
        <Pressable onPress={() => router.push("/exploration" as Href)} style={styles.summaryCard}><MaterialCommunityIcons color="#278DA8" name="map-marker-radius-outline" size={27} /><View style={styles.flex}><View style={styles.cardTitleRow}><Text style={styles.cardTitle}>探索地圖</Text><MaterialCommunityIcons color={colors.textMuted} name="chevron-right" size={22} /></View><Text style={styles.cardText}>用地圖查看過去的旅遊、餐廳、山岳與景點紀錄</Text></View></Pressable>
      </View>

      <Pressable onPress={() => openModule("mood")} style={[styles.summaryCard, styles.fullWidthCard]}><MaterialCommunityIcons color="#A56CC1" name="emoticon-happy-outline" size={27} /><View style={styles.flex}><View style={styles.cardTitleRow}><Text style={styles.cardTitle}>心情趨勢</Text><Pressable onPress={(event) => { event.stopPropagation(); setRecordTarget({ kind: "mood", initial: latestTodayRecord("mood") }); }} style={[styles.measureButton, latestTodayRecord("mood") && styles.updateButton]}><MaterialCommunityIcons color={theme === "dark" ? colors.background : colors.white} name="pencil-outline" size={17} /><Text style={styles.measureButtonText}>{latestTodayRecord("mood") ? "更新紀錄" : "紀錄一下"}</Text></Pressable></View><View style={styles.cardTextRow}><Text style={styles.cardText}>{summary?.mood_count ? "今日最新心情：" : "今日尚未記錄心情"}</Text>{summary?.mood_count ? <Text style={styles.moodEmoji}>{moodEmoji}</Text> : null}</View></View></Pressable>
      </AppShell>

      {savedMessage ? <View accessibilityLiveRegion="polite" style={styles.savedToast}><Text style={styles.savedToastText}>{savedMessage}</Text></View> : null}

      {recordTarget ? <RecordModal authorizedRequest={authorizedRequest} defaults={recordTarget.defaults} initial={recordTarget.initial} kind={recordTarget.kind} onClose={() => setRecordTarget(null)} onSaved={async () => { await Promise.all([reload(), loadPreviews()]); setSavedMessage(recordTarget.initial ? "紀錄已更新" : "紀錄已儲存"); setTimeout(() => setSavedMessage(null), 2400); }} visible /> : null}
      {collectionModalOpen ? <CollectionModal authorizedRequest={authorizedRequest} onClose={() => setCollectionModalOpen(false)} onSaved={async (message) => { await loadPreviews(); setSavedMessage(message); setTimeout(() => setSavedMessage(null), 2400); }} visible /> : null}
    </>
  );
}

const createStyles = (colors: ReturnType<typeof useAppPreferences>["colors"], theme: ReturnType<typeof useAppPreferences>["theme"]) => StyleSheet.create({
  notificationCard: { alignItems: "flex-start", backgroundColor: theme === "dark" ? "#2B2922" : "#FFF8ED", borderColor: theme === "dark" ? "#765D3E" : "#F3D7B4", borderRadius: 18, borderWidth: 1, flexDirection: "row", gap: 14, padding: 18 },
  cardGrid: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  summaryCard: { alignItems: "flex-start", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 17, borderWidth: 1, flexDirection: "row", gap: 13, minWidth: 260, padding: 17, flexGrow: 1, flexBasis: "46%" },
  disabledCard: { backgroundColor: "#E8EBEA", opacity: 0.8 },
  disabledText: { color: colors.textMuted },
  flex: { flex: 1 },
  cardTitleRow: { alignItems: "center", flexDirection: "row", gap: 10, justifyContent: "space-between" },
  cardTitle: { color: colors.text, fontSize: 15, fontWeight: "800" },
  cardText: { color: colors.textMuted, fontSize: 13, lineHeight: 19, marginTop: 4 },
  moodEmoji: { fontSize: 25, lineHeight: 30 },
  inlineText: { alignItems: "baseline", flexDirection: "row", flexWrap: "wrap" },
  cardTextRow: { alignItems: "center", flexDirection: "row", gap: 8 },
  fullWidthCard: { flexBasis: "auto", flexGrow: 0, width: "100%" },
  errorCard: { backgroundColor: "#FFF0F0", borderRadius: 14, gap: 4, padding: 16 },
  errorText: { color: "#A33D3D", fontSize: 13 },
  retry: { color: colors.primary, fontSize: 12, fontWeight: "800" },
  measureButton: { alignItems: "center", backgroundColor: colors.primary, borderRadius: 10, flexDirection: "row", gap: 6, paddingHorizontal: 13, paddingVertical: 9 },
  updateButton: { backgroundColor: "#3B82F6" },
  measureButtonDisabled: { opacity: 0.55 },
  measureButtonText: { color: colors.white, fontSize: 12, fontWeight: "800" },
  modalBackdrop: { alignItems: "center", backgroundColor: "rgba(16, 38, 34, 0.45)", flex: 1, justifyContent: "center", padding: 22 },
  weightModalCard: { backgroundColor: colors.surface, borderRadius: 22, elevation: 12, gap: 20, maxWidth: 540, padding: 26, paddingTop: 54, position: "relative", shadowColor: "#102622", shadowOffset: { height: 10, width: 0 }, shadowOpacity: 0.2, shadowRadius: 24, width: "100%" },
  closeButton: { alignItems: "center", height: 42, justifyContent: "center", position: "absolute", right: 12, top: 10, width: 42 },
  modalTitleRow: { alignItems: "center", flexDirection: "row", gap: 10, justifyContent: "center" },
  modalTitleIcon: { height: 38, width: 38 },
  modalTitle: { color: colors.text, fontSize: 22, fontWeight: "900", textAlign: "center" },
  weightSentence: { alignItems: "center", flexDirection: "row", flexWrap: "wrap", gap: 9, justifyContent: "center" },
  weightSentenceText: { color: colors.text, fontSize: 16, fontWeight: "700" },
  weightInput: { backgroundColor: colors.white, borderColor: colors.border, borderRadius: 12, borderWidth: 2, color: colors.text, fontSize: 18, fontWeight: "800", minWidth: 130, paddingHorizontal: 14, paddingVertical: 11, textAlign: "center" },
  weightInputError: { borderColor: "#B9473E" },
  weightErrorText: { color: "#B9473E", fontSize: 14, fontWeight: "700", lineHeight: 20, textAlign: "center" },
  confirmQuestion: { color: colors.primaryDark, fontSize: 21, fontWeight: "900", lineHeight: 30, textAlign: "center" },
  modalActions: { flexDirection: "row", flexWrap: "wrap", gap: 10, justifyContent: "center" },
  modalButton: { alignItems: "center", borderRadius: 12, minWidth: 108, paddingHorizontal: 18, paddingVertical: 12 },
  cancelButton: { backgroundColor: "#E8EEEC" },
  cancelButtonText: { color: colors.text, fontSize: 14, fontWeight: "800" },
  clearButton: { backgroundColor: "#FFF2E5", borderColor: colors.accent, borderWidth: 1 },
  clearButtonText: { color: "#9B5D20", fontSize: 14, fontWeight: "800" },
  confirmButton: { backgroundColor: colors.primary },
  confirmButtonText: { color: colors.white, fontSize: 14, fontWeight: "800" },
  savedToast: { alignSelf: "center", backgroundColor: colors.primaryDark, borderRadius: 20, bottom: 22, paddingHorizontal: 18, paddingVertical: 10, position: "absolute", zIndex: 20 },
  savedToastText: { color: colors.white, fontWeight: "800" },
});
