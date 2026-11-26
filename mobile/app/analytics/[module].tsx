import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";
import { Redirect, useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, Modal, ScrollView, StyleSheet, useWindowDimensions } from "react-native";

import { AppPressable as Pressable } from "@/components/AppPressable";
import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";
import { AppShell } from "@/components/AppShell";
import { ChartCard, LineChart } from "@/components/Charts";
import { DateRangeFilter, defaultDateRange } from "@/components/DateRangeFilter";
import { RecordModal } from "@/components/RecordModal";
import { SensitiveValue } from "@/components/SensitiveValue";
import { colors } from "@/constants/theme";
import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import {
  getAnalytics,
  deleteRecord,
  type AnalyticsModule,
  type AnalyticsResponseMap,
  type BodyAnalytics,
  type DateRange,
  type FinanceAnalytics,
  type RecordItem,
  type RecordKind,
} from "@/services/analyticsApi";
import { ApiError } from "@/services/authApi";

const MODULES: AnalyticsModule[] = ["body", "finance"];
type BodyTab = "weight" | "diet" | "exercise";

export default function AnalyticsScreen() {
  const params = useLocalSearchParams<{ module?: string }>();
  const module = MODULES.includes(params.module as AnalyticsModule) ? params.module as AnalyticsModule : null;
  const { status, authorizedRequest } = useAuth();
  const { data: dashboard } = useDashboard();
  const [range, setRange] = useState<DateRange>(defaultDateRange);
  const [payload, setPayload] = useState<AnalyticsResponseMap[AnalyticsModule] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ kind: RecordKind; item: RecordItem } | null>(null);
  const [deleting, setDeleting] = useState<{ kind: RecordKind; item: RecordItem } | null>(null);
  const [pendingDeletion, setPendingDeletion] = useState<{ kind: RecordKind; item: RecordItem } | null>(null);
  const [bodyTab, setBodyTab] = useState<BodyTab>("weight");
  const deleteTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scrollViewRef = useRef<ScrollView>(null);

  const load = useCallback(async () => {
    if (!module || status !== "authenticated") return;
    setLoading(true); setError(null);
    try {
      setPayload(await getAnalytics(authorizedRequest, module, range));
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "資料目前無法載入，請稍後再試");
    } finally { setLoading(false); }
  }, [authorizedRequest, module, range, status]);

  useEffect(() => { void load(); }, [load]);

  const scheduleDelete = () => {
    if (!deleting || pendingDeletion) { setDeleting(null); return; }
    const target = deleting;
    setDeleting(null); setPendingDeletion(target); setSavedMessage("已排定刪除，5 秒內可復原");
    deleteTimer.current = setTimeout(() => {
      void deleteRecord(authorizedRequest, target.kind, target.item.id)
        .then(async (result) => { setPendingDeletion(null); setSavedMessage(result.message); setTimeout(() => setSavedMessage(null), 2400); await load(); })
        .catch((requestError) => { setPendingDeletion(null); setSavedMessage(requestError instanceof Error ? requestError.message : "刪除失敗，請重試"); });
    }, 5000);
  };

  const undoDelete = () => {
    if (deleteTimer.current) clearTimeout(deleteTimer.current);
    deleteTimer.current = null; setPendingDeletion(null); setSavedMessage("已復原，資料未刪除"); setTimeout(() => setSavedMessage(null), 2400);
  };

  if (status === "guest") return <Redirect href="/login" />;
  if (!module) return <Redirect href="/home" />;
  const title = dashboard?.navigation[module]?.label ?? "分析頁面";
  const hasAnyData = payload?.has_any_data ?? false;
  const hasRangeData = payload ? rangeHasData(module, payload) : false;
  const initialLoading = loading && !payload;

  return (
    <AppShell scrollViewRef={scrollViewRef} title={title}>
      {!error && module === "body" && payload ? <BodyTabs selected={bodyTab} onSelect={setBodyTab} /> : null}
      {!initialLoading && payload ? (
        <DateRangeFilter
          holidayOnly
          hint="可查任意歷史日期，每次區間最少 1 天、最多 30 天"
          minDays={1}
          onApply={setRange}
          range={range}
        />
      ) : null}
      {initialLoading ? <View style={styles.initialLoading}><ActivityIndicator color={colors.primary} size="large" /><Text style={styles.emptyText}>資料載入中…</Text></View> : null}
      {error ? <View style={styles.errorCard}><Text style={styles.errorText}>{error}</Text><Pressable onPress={() => void load()}><Text style={styles.retry}>重新載入</Text></Pressable></View> : null}
      {!error && payload && !hasRangeData ? <EmptyState hasAnyData={hasAnyData} /> : null}
      {!error && payload ? renderModule(module, payload, bodyTab) : null}
      {!error && payload ? <EditableRecords bodyTab={bodyTab} module={module} onDelete={setDeleting} onEdit={setEditing} payload={payload} /> : null}
      {savedMessage ? <View style={styles.savedToast}><Text style={styles.savedText}>{savedMessage}</Text>{pendingDeletion ? <Pressable onPress={undoDelete}><Text style={styles.undoText}>復原</Text></Pressable> : null}</View> : null}
      {editing ? <RecordModal authorizedRequest={authorizedRequest} initial={editing.item} kind={editing.kind} onClose={() => setEditing(null)} onSaved={async () => { await load(); setSavedMessage("紀錄已更新"); setTimeout(() => setSavedMessage(null), 2400); }} visible /> : null}
      <Modal animationType="fade" onRequestClose={() => setDeleting(null)} transparent visible={Boolean(deleting)}><View style={styles.deleteBackdrop}><View style={styles.deleteCard}><Text style={styles.deleteTitle}>確認刪除？</Text><Text style={styles.bodyText}>確認後有 5 秒可復原，逾時才會正式刪除。</Text><View style={styles.recordActions}><Pressable onPress={() => setDeleting(null)} style={[styles.recordButton, styles.editButton]}><Text style={styles.recordButtonText}>取消</Text></Pressable><Pressable disabled={Boolean(pendingDeletion)} onPress={scheduleDelete} style={[styles.recordButton, styles.deleteButton]}><Text style={styles.deleteButtonText}>刪除</Text></Pressable></View></View></View></Modal>
    </AppShell>
  );
}

function EditableRecords({ bodyTab, module, onDelete, onEdit, payload }: { bodyTab: BodyTab; module: AnalyticsModule; onDelete: (value: { kind: RecordKind; item: RecordItem }) => void; onEdit: (value: { kind: RecordKind; item: RecordItem }) => void; payload: AnalyticsResponseMap[AnalyticsModule] }) {
  const { height: windowHeight } = useWindowDimensions();
  let groups: Array<{ kind: RecordKind; label: string; records: RecordItem[]; latest?: RecordItem | null }> = [];
  if (module === "finance") { const value = payload as FinanceAnalytics; groups = [{ kind: "finance", label: "日期區間收支紀錄", records: value.records, latest: value.latest_record }]; }
  if (module === "body") { const value = payload as BodyAnalytics; const config = { weight: { label: "日期區間體態紀錄", records: value.weight_records, latest: value.latest_records.weight }, diet: { label: "日期區間飲食紀錄", records: value.diet_records, latest: value.latest_records.diet }, exercise: { label: "日期區間運動紀錄", records: value.exercise_records, latest: value.latest_records.exercise } }[bodyTab]; groups = [{ kind: bodyTab, ...config }]; }
  if (!groups.length) return null;
  const recordCard = (group: typeof groups[number], item: RecordItem, latest: boolean) => <View key={`${group.kind}-${item.id}-${latest ? "latest" : "range"}`} style={styles.listCard}>{group.kind === "weight" ? <View style={styles.bodyRecordValues}><SensitiveRow label="身高" value={item.height_cm == null ? null : `${Number(item.height_cm).toFixed(1)} 公分`} /><SensitiveRow label="體重" value={item.weight_kg == null ? null : `${Number(item.weight_kg).toFixed(1)} 公斤`} /><SensitiveRow label="腰圍" value={item.waist_cm == null ? null : `${Number(item.waist_cm).toFixed(1)} 公分`} /><SensitiveRow label="BMI" unavailable="無法計算" value={item.bmi == null ? null : Number(item.bmi).toFixed(2)} /></View> : group.kind === "finance" ? <View style={styles.inlineSensitive}><Text style={styles.itemTitle}>{item.type === "income" ? "收入" : "支出"}｜{String(item.category)}｜</Text><SensitiveValue style={styles.itemTitle}>{`${Number(item.amount).toLocaleString()} 元`}</SensitiveValue></View> : <Text style={styles.itemTitle}>{recordSummary(group.kind, item)}</Text>}<Text style={styles.meta}>{String(item.date ?? item.entry_date ?? "")}</Text>{latest && item.can_edit ? <View style={styles.recordActions}><Pressable onPress={() => onEdit({ kind: group.kind, item })} style={[styles.recordButton, styles.editButton]}><Text style={styles.recordButtonText}>編輯</Text></Pressable><Pressable onPress={() => onDelete({ kind: group.kind, item })} style={[styles.recordButton, styles.deleteButton]}><Text style={styles.deleteButtonText}>刪除</Text></Pressable></View> : latest ? <Text style={styles.telegramHint}>歷史紀錄請至 Telegram 管理。</Text> : null}</View>;
  return <>{groups.map((group) => <View key={group.kind} style={styles.recordGroup}><Section title={group.label}><ScrollView contentContainerStyle={styles.rangeRecordContent} nestedScrollEnabled style={{ maxHeight: windowHeight * 0.6 }}>{group.records.length ? group.records.map((item) => recordCard(group, item, false)) : <Text style={styles.todoEmptyText}>這段期間沒有紀錄</Text>}</ScrollView></Section>{group.latest !== undefined ? <Section title="最近紀錄">{group.latest ? recordCard(group, group.latest, true) : <Text style={styles.todoEmptyText}>尚無紀錄</Text>}</Section> : null}</View>)}</>;
}

function SensitiveRow({ label, unavailable = "尚無紀錄", value }: { label: string; unavailable?: string; value: string | null }) { return <View style={styles.inlineSensitive}><Text style={styles.bodyRecordValue}>{label}：</Text>{value ? <SensitiveValue style={styles.bodyRecordValue}>{value}</SensitiveValue> : <Text style={styles.bodyRecordValue}>{unavailable}</Text>}</View>; }

function recordSummary(kind: RecordKind, item: RecordItem): string {
  if (kind === "finance") return `${item.type === "income" ? "收入" : "支出"}｜${String(item.category)}｜${Number(item.amount).toLocaleString()} 元`;
  if (kind === "diet") return String(item.description ?? "飲食紀錄");
  if (kind === "exercise") return `${String(item.activity)}｜${String(item.duration_minutes)} 分鐘`;
  return `${Number(item.weight_kg).toFixed(1)} 公斤${item.waist_cm == null ? "" : `｜腰圍 ${Number(item.waist_cm).toFixed(1)} 公分`}`;
}

function rangeHasData(module: AnalyticsModule, payload: AnalyticsResponseMap[AnalyticsModule]): boolean {
  switch (module) {
    case "body": { const value = payload as BodyAnalytics; return value.weight.length + value.diet.length + value.exercise.length > 0; }
    case "finance": return (payload as FinanceAnalytics).daily.length > 0;
  }
}

function renderModule(module: AnalyticsModule, payload: AnalyticsResponseMap[AnalyticsModule], bodyTab: BodyTab) {
  switch (module) {
    case "body": return <BodyView data={payload as BodyAnalytics} selected={bodyTab} />;
    case "finance": return <FinanceView data={payload as FinanceAnalytics} />;
  }
}

function BodyTabs({ onSelect, selected }: { onSelect: (value: BodyTab) => void; selected: BodyTab }) {
  const tabs: Array<{ key: BodyTab; label: string }> = [{ key: "weight", label: "體態" }, { key: "diet", label: "飲食" }, { key: "exercise", label: "運動" }];
  return <View style={styles.tabs}>{tabs.map((tab) => <Pressable key={tab.key} onPress={() => onSelect(tab.key)} style={[styles.tab, selected === tab.key && styles.tabSelected]}><Text style={[styles.tabText, selected === tab.key && styles.tabTextSelected]}>{tab.label}</Text></Pressable>)}</View>;
}

function EmptyState({ hasAnyData }: { hasAnyData: boolean }) {
  return <View style={styles.empty}><MaterialCommunityIcons color={colors.textMuted} name="database-off-outline" size={42} /><Text style={styles.emptyText}>{hasAnyData ? "這段期間沒有任何紀錄" : "未找到任何一筆資料！"}</Text></View>;
}

function BodyView({ data, selected }: { data: BodyAnalytics; selected: BodyTab }) {
  const dietTooltip = (row: BodyAnalytics["diet"][number], nutrient: "fat_g" | "protein_g" | "carbs_g" | "calories", unit: string) => `${row.date}｜人工 ${row[`manual_${nutrient}`]} ${unit}｜AI ${row[`ai_${nutrient}`]} ${unit}｜合計 ${row[`total_${nutrient}`]} ${unit}`;
  const exerciseTooltip = (row: BodyAnalytics["exercise"][number]) => `${row.date}｜人工 ${row.manual_calories} 大卡｜AI ${row.ai_calories} 大卡｜合計 ${row.total_calories} 大卡`;
  if (selected === "weight") return <>
    <ChartCard title="體重趨勢"><LineChart yAxisLabel="體重(公斤)" series={[{ label: "體重", color: "#2E9D74", marker: "solid", points: data.weight.map((row) => ({ label: row.date, value: row.weight })) }]} /></ChartCard>
    <ChartCard title="腰圍趨勢"><LineChart yAxisLabel="腰圍(公分)" series={[{ label: "腰圍", color: "#D9544D", marker: "solid", points: data.weight.map((row) => ({ label: row.date, value: row.waist })) }]} /></ChartCard>
    <ChartCard title="BMI 趨勢"><LineChart yAxisLabel="BMI" series={[{ label: "BMI", color: "#3B82F6", marker: "solid", points: data.weight.map((row) => ({ label: row.date, value: row.bmi })) }]} /></ChartCard>
  </>;
  if (selected === "diet") return <>
    <View style={styles.metricRow}><Metric label="熱量合計" value={`${data.diet.reduce((sum, row) => sum + row.total_calories, 0).toLocaleString()} 大卡`} /><Metric label="飲水合計" value={`${data.diet.reduce((sum, row) => sum + row.water_ml, 0).toLocaleString()} ml`} /></View>
    <ChartCard title="熱量趨勢"><LineChart yAxisLabel="熱量(大卡)" series={[
      { label: "熱量（人工）", color: "#D9544D", marker: "solid", points: data.diet.map((row) => ({ label: row.date, tooltip: dietTooltip(row, "calories", "大卡"), value: row.manual_count ? row.manual_calories : null })) },
      { label: "熱量（AI）", color: "#D9544D", marker: "hollow", points: data.diet.map((row) => ({ label: row.date, tooltip: dietTooltip(row, "calories", "大卡"), value: row.ai_count ? row.ai_calories : null })) },
    ]} zeroBased /><Text style={styles.aiEstimateNotice}>提醒：實心圓為人工輸入，空心圓為 AI 估算；AI 結果未必是最準確的數值喔！</Text></ChartCard>
    <ChartCard title="營養素趨勢"><LineChart yAxisLabel="營養素(公克)" series={([ ["脂肪", "fat_g", "#EB9741", "g"], ["蛋白質", "protein_g", "#2E9D74", "g"], ["碳水", "carbs_g", "#A56CC1", "g"] ] as const).map(([label, key, color, unit]) => ({ label, color, marker: "solid" as const, points: data.diet.map((row) => ({ label: row.date, tooltip: dietTooltip(row, key, unit), value: row[`total_${key}`] })) }))} zeroBased /></ChartCard>
    <ChartCard title="飲水趨勢"><LineChart yAxisLabel="飲水量(ml)" series={[{ label: "飲水", color: "#3B82F6", marker: "solid", points: data.diet.map((row) => ({ label: row.date, value: row.water_ml })) }]} zeroBased /></ChartCard>
  </>;
  return <>
    <View style={styles.metricRow}><Metric label="運動時間" value={`${data.exercise.reduce((sum, row) => sum + row.minutes, 0).toLocaleString()} 分鐘`} /><Metric label="消耗熱量" value={`${data.exercise.reduce((sum, row) => sum + row.total_calories, 0).toLocaleString()} 大卡`} /></View>
    <ChartCard title="運動時間趨勢"><LineChart yAxisLabel="時間(分鐘)" series={[{ label: "分鐘", color: "#2E9D74", marker: "solid", points: data.exercise.map((row) => ({ label: row.date, value: row.minutes })) }]} zeroBased /></ChartCard>
    <ChartCard title="運動消耗趨勢"><LineChart yAxisLabel="熱量(大卡)" series={[
      { label: "消耗大卡（人工）", color: "#EB9741", marker: "solid", points: data.exercise.map((row) => ({ label: row.date, tooltip: exerciseTooltip(row), value: row.manual_count ? row.manual_calories : null })) },
      { label: "消耗大卡（AI）", color: "#EB9741", marker: "hollow", points: data.exercise.map((row) => ({ label: row.date, tooltip: exerciseTooltip(row), value: row.ai_count ? row.ai_calories : null })) },
    ]} zeroBased /><Text style={styles.aiEstimateNotice}>提醒：實心圓為人工輸入，空心圓為 AI 估算；AI 結果未必是最準確的數值喔！</Text></ChartCard>
  </>;
}

function FinanceView({ data }: { data: FinanceAnalytics }) {
  return <><View style={styles.metricRow}><Metric label="收入合計" sensitive value={`${data.income_total.toLocaleString()} 元`} /><Metric label="支出合計" sensitive value={`${data.expense_total.toLocaleString()} 元`} /><Metric label="結餘" sensitive value={`${(data.income_total - data.expense_total).toLocaleString()} 元`} /></View><ChartCard title="收支比較"><LineChart yAxisLabel="台幣金額(元)" zeroBased series={[{ label: "收入", color: "#2E9D74", points: data.daily.map((row) => ({ label: row.date, value: row.income })) }, { label: "支出", color: "#EB9741", points: data.daily.map((row) => ({ label: row.date, value: row.expense })) }]} /></ChartCard></>;
}

function Section({ children, title }: { children: React.ReactNode; title: string }) { return <View style={styles.section}><Text style={styles.sectionTitle}>{title}</Text>{children}</View>; }
function Metric({ label, sensitive = false, value }: { label: string; sensitive?: boolean; value: string }) { return <View style={styles.metric}><Text style={styles.metricLabel}>{label}</Text>{sensitive ? <SensitiveValue style={styles.metricValue}>{value}</SensitiveValue> : <Text style={styles.metricValue}>{value}</Text>}</View>; }

const styles = StyleSheet.create({
  initialLoading: { alignItems: "center", gap: 12, justifyContent: "center", minHeight: 360 },
  errorCard: { backgroundColor: "#FFF0F0", borderRadius: 14, gap: 7, padding: 16 }, errorText: { color: "#A33D3D" }, retry: { color: colors.primary, fontWeight: "800" },
  empty: { alignItems: "center", gap: 12, justifyContent: "center", minHeight: 240 }, emptyText: { color: colors.textMuted, fontSize: 15, fontWeight: "700" }, aiEstimateNotice: { color: colors.accent, fontSize: 13, fontWeight: "800", lineHeight: 20, textAlign: "center" },
  section: { gap: 10 }, sectionTitle: { color: colors.text, fontSize: 18, fontWeight: "900", marginTop: 5 },
  listCard: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 15, borderWidth: 1, gap: 6, padding: 15 }, itemTitle: { color: colors.text, fontSize: 15, fontWeight: "800" }, meta: { color: colors.textMuted, fontSize: 11 }, bodyText: { color: colors.text, fontSize: 13, lineHeight: 20 },
  metricRow: { flexDirection: "row", flexWrap: "wrap", gap: 12 }, metric: { backgroundColor: colors.surface, borderRadius: 15, flex: 1, minWidth: 150, padding: 17 }, metricLabel: { color: colors.textMuted, fontSize: 12 }, metricValue: { color: colors.text, fontSize: 24, fontWeight: "900", marginTop: 5 },
  savedToast: { alignItems: "center", alignSelf: "center", backgroundColor: colors.primaryDark, borderRadius: 20, bottom: 22, flexDirection: "row", gap: 14, paddingHorizontal: 18, paddingVertical: 10, position: "absolute", zIndex: 10 }, savedText: { color: colors.white, fontWeight: "700" }, undoText: { color: "#FFD18A", fontWeight: "900", textDecorationLine: "underline" },
  recordActions: { flexDirection: "row", flexWrap: "wrap", gap: 8, justifyContent: "flex-end", marginTop: 6 }, recordButton: { borderRadius: 9, minHeight: 40, paddingHorizontal: 14, paddingVertical: 10 }, editButton: { backgroundColor: colors.primarySoft }, deleteButton: { backgroundColor: "#FAD7D5" }, recordButtonText: { color: colors.primaryDark, fontWeight: "800" }, deleteButtonText: { color: colors.danger, fontWeight: "800" }, telegramHint: { color: colors.textMuted, fontSize: 11, marginTop: 4 },
  bodyRecordValues: { gap: 6 }, bodyRecordValue: { color: colors.text, fontSize: 15, fontWeight: "700" }, inlineSensitive: { alignItems: "baseline", flexDirection: "row", flexWrap: "wrap" },
  tabs: { backgroundColor: colors.border, borderRadius: 12, flexDirection: "row", overflow: "hidden" }, tab: { alignItems: "center", flex: 1, paddingVertical: 11 }, tabSelected: { backgroundColor: colors.primarySoft }, tabText: { color: colors.textMuted, fontSize: 15, fontWeight: "800" }, tabTextSelected: { color: colors.primaryDark },
  rangeRecordContent: { gap: 10 }, recordGroup: { gap: 14 }, todoEmptyText: { color: colors.textMuted, fontSize: 12 },
  deleteBackdrop: { alignItems: "center", backgroundColor: "rgba(16,38,34,.45)", flex: 1, justifyContent: "center", padding: 20 }, deleteCard: { backgroundColor: colors.surface, borderRadius: 20, gap: 16, maxWidth: 420, padding: 24, width: "100%" }, deleteTitle: { color: colors.text, fontSize: 21, fontWeight: "900" },
});
