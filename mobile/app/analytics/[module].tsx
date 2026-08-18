import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";
import { Redirect, useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Calendar, type DateData } from "react-native-calendars";
import { ActivityIndicator, Modal, ScrollView, StyleSheet } from "react-native";

import { AppPressable as Pressable } from "@/components/AppPressable";
import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";
import { AppShell } from "@/components/AppShell";
import { BarChart, ChartCard, FunnelChart, LineChart, PieChart } from "@/components/Charts";
import { DateRangeFilter, defaultDateRange, SingleDateFilter, todayIsoDate } from "@/components/DateRangeFilter";
import { RecordModal } from "@/components/RecordModal";
import { SensitiveValue } from "@/components/SensitiveValue";
import { colors } from "@/constants/theme";
import { useAppPreferences } from "@/context/AppPreferencesContext";
import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import {
  getAnalytics,
  deleteRecord,
  type AnalyticsModule,
  type AnalyticsResponseMap,
  type BodyAnalytics,
  type DateRange,
  type ExamsAnalytics,
  type FinanceAnalytics,
  type JobsAnalytics,
  type MoodAnalytics,
  type RecordItem,
  type RecordKind,
  type SkillsAnalytics,
  type TodoAnalytics,
} from "@/services/analyticsApi";
import { IMPORTANT_DAY_COLOR, uniqueImportantDayLabels } from "@/utils/calendarLabels";
import { ApiError } from "@/services/authApi";

const MODULES: AnalyticsModule[] = ["todos", "body", "finance", "mood", "jobs", "exams", "skills"];
const MOOD_SCORE: Record<string, number> = { angry_anxious: 1, sad_down: 2, tired_burned_out: 2.5, neutral: 3, calm_relaxed: 4, happy_excited: 5 };
const MOOD_LABEL: Record<string, string> = { angry_anxious: "😡 生氣／焦慮", sad_down: "😢 難過／低落", tired_burned_out: "🫠 疲憊／厭世", neutral: "🙂 普通／平淡", calm_relaxed: "😌 平靜／放鬆", happy_excited: "🥳 高興／興奮" };
const TODO_STATUS: Record<string, { backgroundColor: string; label: string }> = {
  expired: { backgroundColor: "#E1E4E3", label: "已過期" },
  pending: { backgroundColor: "#FAD7D5", label: "待處理" },
  completed: { backgroundColor: "#D7EFE2", label: "已完成" },
  cancelled: { backgroundColor: "#E8D7C5", label: "已取消" },
};

export default function AnalyticsScreen() {
  const params = useLocalSearchParams<{ module?: string }>();
  const module = MODULES.includes(params.module as AnalyticsModule) ? params.module as AnalyticsModule : null;
  const { status, authorizedRequest } = useAuth();
  const { data: dashboard } = useDashboard();
  const [range, setRange] = useState<DateRange>(defaultDateRange);
  const [calendarMonth, setCalendarMonth] = useState(defaultDateRange().end.slice(0, 7));
  const [skillDate, setSkillDate] = useState(todayIsoDate);
  const [payload, setPayload] = useState<AnalyticsResponseMap[AnalyticsModule] | null>(null);
  const [filterCalendarDays, setFilterCalendarDays] = useState<TodoAnalytics["calendar_days"]>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ kind: RecordKind; item: RecordItem } | null>(null);
  const [deleting, setDeleting] = useState<{ kind: RecordKind; item: RecordItem } | null>(null);
  const [pendingDeletion, setPendingDeletion] = useState<{ kind: RecordKind; item: RecordItem } | null>(null);
  const deleteTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scrollViewRef = useRef<ScrollView>(null);

  const load = useCallback(async () => {
    if (!module || status !== "authenticated") return;
    setLoading(true); setError(null);
    try {
      const selectedRange = module === "skills"
        ? { start: skillDate, end: skillDate }
        : range;
      setPayload(await getAnalytics(
        authorizedRequest,
        module,
        selectedRange,
        module === "todos" ? { calendarMonth } : undefined,
      ));
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "資料目前無法載入，請稍後再試");
    } finally { setLoading(false); }
  }, [authorizedRequest, calendarMonth, module, range, skillDate, status]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => setCalendarMonth(range.end.slice(0, 7)), [range.end]);
  useEffect(() => {
    if (!module || module === "todos" || status !== "authenticated") return;
    const dateInMonth = `${calendarMonth}-01`;
    void getAnalytics(authorizedRequest, "todos", { start: dateInMonth, end: dateInMonth }, { calendarMonth })
      .then((result) => setFilterCalendarDays(result.calendar_days ?? {}))
      .catch(() => setFilterCalendarDays({}));
  }, [authorizedRequest, calendarMonth, module, status]);

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

  return (
    <AppShell scrollViewRef={scrollViewRef} title={title}>
      {module === "skills" ? (
        <SingleDateFilter calendarDays={filterCalendarDays} date={skillDate} onCalendarMonthChange={setCalendarMonth} onApply={setSkillDate} />
      ) : (
        <DateRangeFilter
          allowFuture={module === "todos"}
          calendarCounts={module === "todos" ? (payload as TodoAnalytics | null)?.calendar_counts : undefined}
          calendarDays={module === "todos" ? (payload as TodoAnalytics | null)?.calendar_days : filterCalendarDays}
          holidayOnly={module !== "todos"}
          hint={module === "todos" ? "可查任意日期，每次區間最少 1 天、最多 7 天" : undefined}
          maxDays={module === "todos" ? 7 : undefined}
          minDays={module === "todos" ? 1 : undefined}
          onCalendarMonthChange={setCalendarMonth}
          onApply={setRange}
          range={range}
        />
      )}
      {loading ? <ActivityIndicator color={colors.primary} size="large" /> : null}
      {error ? <View style={styles.errorCard}><Text style={styles.errorText}>{error}</Text><Pressable onPress={() => void load()}><Text style={styles.retry}>重新載入</Text></Pressable></View> : null}
      {!loading && !error && payload && !hasRangeData && module !== "todos" ? <EmptyState hasAnyData={hasAnyData} /> : null}
      {!loading && !error && payload && (hasRangeData || module === "todos") ? renderModule(module, payload, range, calendarMonth, setCalendarMonth, scrollViewRef) : null}
      {!loading && !error && payload ? <EditableRecords module={module} onDelete={setDeleting} onEdit={setEditing} payload={payload} /> : null}
      {savedMessage ? <View style={styles.savedToast}><Text style={styles.savedText}>{savedMessage}</Text>{pendingDeletion ? <Pressable onPress={undoDelete}><Text style={styles.undoText}>復原</Text></Pressable> : null}</View> : null}
      {editing ? <RecordModal authorizedRequest={authorizedRequest} initial={editing.item} kind={editing.kind} onClose={() => setEditing(null)} onSaved={async () => { await load(); setSavedMessage("紀錄已更新"); setTimeout(() => setSavedMessage(null), 2400); }} visible /> : null}
      <Modal animationType="fade" onRequestClose={() => setDeleting(null)} transparent visible={Boolean(deleting)}><View style={styles.deleteBackdrop}><View style={styles.deleteCard}><Text style={styles.deleteTitle}>確認刪除？</Text><Text style={styles.bodyText}>確認後有 5 秒可復原，逾時才會正式刪除。</Text><View style={styles.recordActions}><Pressable onPress={() => setDeleting(null)} style={[styles.recordButton, styles.editButton]}><Text style={styles.recordButtonText}>取消</Text></Pressable><Pressable disabled={Boolean(pendingDeletion)} onPress={scheduleDelete} style={[styles.recordButton, styles.deleteButton]}><Text style={styles.deleteButtonText}>刪除</Text></Pressable></View></View></View></Modal>
    </AppShell>
  );
}

function EditableRecords({ module, onDelete, onEdit, payload }: { module: AnalyticsModule; onDelete: (value: { kind: RecordKind; item: RecordItem }) => void; onEdit: (value: { kind: RecordKind; item: RecordItem }) => void; payload: AnalyticsResponseMap[AnalyticsModule] }) {
  let groups: Array<{ kind: RecordKind; label: string; records: RecordItem[]; goalText?: string }> = [];
  if (module === "todos") groups = [{ kind: "todo", label: "待辦紀錄管理", records: (payload as TodoAnalytics).items as unknown as RecordItem[] }];
  if (module === "finance") groups = [{ kind: "finance", label: "收支紀錄管理", records: (payload as FinanceAnalytics).records }];
  if (module === "mood") groups = [{ kind: "mood", label: "心情紀錄管理", records: (payload as MoodAnalytics).items as unknown as RecordItem[] }];
  if (module === "body") { const value = payload as BodyAnalytics; const goal = value.goals.find((item) => item.goal_type === "weight"); const goalText = goal ? `目標：${goal.target_date ? String(goal.target_date).slice(2) : "未設定日期"} ${goal.target_description}` : "未設定目標"; groups = [{ kind: "weight", label: "體態紀錄管理", records: value.latest_body_record ? [value.latest_body_record] : [], goalText }, { kind: "diet", label: "飲食紀錄管理", records: value.diet_records }, { kind: "exercise", label: "運動紀錄管理", records: value.exercise_records }]; }
  if (!groups.length) return null;
  return <>{groups.map((group) => <Section key={group.kind} title={group.label}>{group.records.length ? group.records.map((item) => { const recordDate = String(item.date ?? item.entry_date ?? item.due_at ?? "").slice(0, 10); const isLegacyDailyRecord = (["diet", "weight", "mood"] as RecordKind[]).includes(group.kind) && recordDate === todayIsoDate(); return <View key={`${group.kind}-${item.id}`} style={styles.listCard}>{group.kind === "weight" ? <View style={styles.bodyRecordValues}><SensitiveRow label="身高" value={item.height_cm == null ? null : `${Number(item.height_cm).toFixed(1)} 公分`} /><SensitiveRow label="體重" value={item.weight_kg == null ? null : `${Number(item.weight_kg).toFixed(1)} 公斤`} /><SensitiveRow label="腰圍" value={item.waist_cm == null ? null : `${Number(item.waist_cm).toFixed(1)} 公分`} /><SensitiveRow label="BMI" unavailable="無法計算" value={item.bmi == null ? null : Number(item.bmi).toFixed(2)} /></View> : group.kind === "finance" ? <View style={styles.inlineSensitive}><Text style={styles.itemTitle}>{item.type === "income" ? "收入" : "支出"}｜{String(item.category)}｜</Text><SensitiveValue style={styles.itemTitle}>{`${Number(item.amount).toLocaleString()} 元`}</SensitiveValue></View> : <Text style={styles.itemTitle}>{recordSummary(group.kind, item)}</Text>}<Text style={styles.meta}>{String(item.date ?? item.entry_date ?? item.due_at ?? "")}</Text>{item.can_edit ? <View style={styles.recordActions}><Pressable onPress={() => onEdit({ kind: group.kind, item })} style={[styles.recordButton, styles.editButton]}><Text style={styles.recordButtonText}>編輯</Text></Pressable><Pressable onPress={() => onDelete({ kind: group.kind, item })} style={[styles.recordButton, styles.deleteButton]}><Text style={styles.deleteButtonText}>刪除</Text></Pressable></View> : <Text style={styles.telegramHint}>{isLegacyDailyRecord ? "今日僅能異動最新一筆紀錄。" : "若需異動其他日期的紀錄，請使用 Telegram。"}</Text>}{group.kind === "weight" ? <Text style={styles.bodyGoalText}>{group.goalText}</Text> : null}</View>; }) : <Text style={styles.todoEmptyText}>{group.kind === "weight" ? "尚無體態紀錄" : "這段期間沒有紀錄"}</Text>}</Section>)}</>;
}

function SensitiveRow({ label, unavailable = "尚無紀錄", value }: { label: string; unavailable?: string; value: string | null }) { return <View style={styles.inlineSensitive}><Text style={styles.bodyRecordValue}>{label}：</Text>{value ? <SensitiveValue style={styles.bodyRecordValue}>{value}</SensitiveValue> : <Text style={styles.bodyRecordValue}>{unavailable}</Text>}</View>; }

function recordSummary(kind: RecordKind, item: RecordItem): string {
  if (kind === "todo") return String(item.content ?? "待辦事項");
  if (kind === "finance") return `${item.type === "income" ? "收入" : "支出"}｜${String(item.category)}｜${Number(item.amount).toLocaleString()} 元`;
  if (kind === "diet") return String(item.description ?? "飲食紀錄");
  if (kind === "exercise") return `${String(item.activity)}｜${String(item.duration_minutes)} 分鐘`;
  if (kind === "weight") return `${Number(item.weight_kg).toFixed(1)} 公斤${item.waist_cm == null ? "" : `｜腰圍 ${Number(item.waist_cm).toFixed(1)} 公分`}`;
  return `${MOOD_LABEL[String(item.mood_category)] ?? "心情"}${item.content ? `｜${String(item.content)}` : ""}`;
}

function rangeHasData(module: AnalyticsModule, payload: AnalyticsResponseMap[AnalyticsModule]): boolean {
  switch (module) {
    case "todos": return (payload as TodoAnalytics).items.length > 0;
    case "body": { const value = payload as BodyAnalytics; return value.weight.length + value.diet.length + value.exercise.length > 0; }
    case "finance": return (payload as FinanceAnalytics).daily.length > 0;
    case "mood": return (payload as MoodAnalytics).items.length > 0;
    case "jobs": { const value = payload as JobsAnalytics; return value.recommendations.length + value.timeline.length + Object.values(value.score_distribution).reduce((sum, count) => sum + count, 0) > 0; }
    case "exams": { const value = payload as ExamsAnalytics; return value.goals.length + value.official_scores.length + value.practice.length > 0; }
    case "skills": { const value = payload as SkillsAnalytics; return value.digests.length + value.videos.length > 0; }
  }
}

function renderModule(
  module: AnalyticsModule,
  payload: AnalyticsResponseMap[AnalyticsModule],
  range: DateRange,
  calendarMonth: string,
  setCalendarMonth: React.Dispatch<React.SetStateAction<string>>,
  scrollViewRef: React.RefObject<ScrollView | null>,
) {
  switch (module) {
    case "todos": return <TodoView calendarMonth={calendarMonth} data={payload as TodoAnalytics} range={range} scrollViewRef={scrollViewRef} setCalendarMonth={setCalendarMonth} />;
    case "body": return <BodyView data={payload as BodyAnalytics} />;
    case "finance": return <FinanceView data={payload as FinanceAnalytics} />;
    case "mood": return <MoodView data={payload as MoodAnalytics} />;
    case "jobs": return <JobsView data={payload as JobsAnalytics} />;
    case "exams": return <ExamsView data={payload as ExamsAnalytics} />;
    case "skills": return <SkillsView data={payload as SkillsAnalytics} />;
  }
}

function EmptyState({ hasAnyData }: { hasAnyData: boolean }) {
  return <View style={styles.empty}><MaterialCommunityIcons color={colors.textMuted} name="database-off-outline" size={42} /><Text style={styles.emptyText}>{hasAnyData ? "這段期間沒有任何紀錄" : "未找到任何一筆資料！"}</Text></View>;
}

function TodoView({ calendarMonth, data, range, scrollViewRef, setCalendarMonth }: { calendarMonth: string; data: TodoAnalytics; range: DateRange; scrollViewRef: React.RefObject<ScrollView | null>; setCalendarMonth: React.Dispatch<React.SetStateAction<string>> }) {
  const { colors: themedColors, theme } = useAppPreferences();
  const dateOf = (value: string) => new Date(value).toLocaleDateString("en-CA", { timeZone: "Asia/Taipei" });
  const grouped = useMemo(() => data.items.reduce<Record<string, TodoAnalytics["items"]>>((result, item) => { const start = dateOf(item.start_at ?? item.due_at); const end = dateOf(item.due_at); const cursor = new Date(`${start}T00:00:00Z`); const last = new Date(`${end}T00:00:00Z`); while (cursor <= last) { const day = cursor.toISOString().slice(0, 10); (result[day] ??= []).push(item); cursor.setUTCDate(cursor.getUTCDate() + 1); } return result; }, {}), [data.items]);
  const todoPageOffset = useRef(0);
  const sectionOffsets = useRef<Record<string, number>>({});
  const [highlightedDate, setHighlightedDate] = useState<string | null>(null);
  const rangeDates = useMemo(() => {
    const dates: string[] = [];
    const cursor = new Date(`${range.start}T00:00:00Z`);
    const lastDay = new Date(`${range.end}T00:00:00Z`);
    while (cursor <= lastDay) {
      dates.push(cursor.toISOString().slice(0, 10));
      cursor.setUTCDate(cursor.getUTCDate() + 1);
    }
    return dates;
  }, [range.end, range.start]);
  const markedDates = useMemo(() => {
    const markings: Record<string, { startingDay?: boolean; endingDay?: boolean; color?: string; textColor?: string }> = {};
    rangeDates.forEach((day) => {
      const isStart = day === range.start;
      const isEnd = day === range.end;
      markings[day] = {
        startingDay: isStart,
        endingDay: isEnd,
        color: isStart || isEnd ? themedColors.primary : theme === "dark" ? "#28574F" : "#D6EEE8",
        textColor: isStart || isEnd ? (theme === "dark" ? themedColors.background : themedColors.white) : themedColors.text,
      };
    });
    return markings;
  }, [range.end, range.start, rangeDates, theme, themedColors]);

  const jumpToDate = (day: DateData) => {
    if (!rangeDates.includes(day.dateString)) return;
    const offset = sectionOffsets.current[day.dateString];
    if (offset === undefined) return;
    scrollViewRef.current?.scrollTo({ animated: true, y: Math.max(0, todoPageOffset.current + offset - 12) });
    setHighlightedDate(day.dateString);
  };

  return <View onLayout={(event) => { todoPageOffset.current = event.nativeEvent.layout.y; }} style={styles.todoCalendarPage}><View style={styles.calendarCard}><Calendar current={`${calendarMonth}-01`} dayComponent={({ date, marking, state }) => { if (!date) return null; const inRange = Boolean(marking); const isToday = date.dateString === todayIsoDate(); const holiday = data.calendar_days?.[date.dateString]; const count = data.calendar_counts[date.dateString] ?? 0; const countColor = theme === "dark" ? themedColors.accent : "#111111"; return <Pressable disabled={!inRange} onPress={() => jumpToDate(date)} style={[styles.calendarDay, inRange && { backgroundColor: marking?.color }, marking?.startingDay && styles.calendarRangeStart, marking?.endingDay && styles.calendarRangeEnd, isToday && (inRange ? styles.calendarTodayInRange : styles.calendarTodayStandalone)]}><Text style={[styles.calendarDayText, state === "disabled" && styles.calendarDisabledText, marking?.textColor ? { color: marking.textColor } : null, holiday?.is_holiday && !isToday && styles.calendarHolidayText, isToday && styles.calendarTodayText]}>{date.day}</Text>{count > 0 ? <Text style={[styles.todoCount, { color: countColor }]}>{count}件</Text> : <View style={styles.todoCountPlaceholder} />}{holiday?.name ? <Text numberOfLines={1} style={styles.calendarHolidayName}>{holiday.name}</Text> : <View style={styles.calendarHolidayPlaceholder} />}{uniqueImportantDayLabels(holiday).map((message) => <Text key={message} numberOfLines={1} style={styles.todoNotificationName}>{message}</Text>)}</Pressable>; }} markedDates={markedDates} markingType="period" onDayPress={jumpToDate} onMonthChange={(month) => setCalendarMonth(month.dateString.slice(0, 7))} theme={{ arrowColor: themedColors.primary, calendarBackground: themedColors.surface, dayTextColor: themedColors.text, monthTextColor: themedColors.text, textSectionTitleColor: themedColors.textMuted, textDisabledColor: theme === "dark" ? "#52645F" : "#D6DEDC", todayTextColor: themedColors.danger }} /></View>{rangeDates.map((day) => { const items = grouped[day] ?? []; const holiday = data.calendar_days?.[day]; return <View key={day} onLayout={(event) => { sectionOffsets.current[day] = event.nativeEvent.layout.y; }} style={[styles.todoDayCard, highlightedDate === day && styles.todoDayCardHighlighted]}><Text style={styles.todoDayTitle}>{day} 待辦事項</Text>{holiday?.name ? <Text style={styles.todoHolidayTitle}>{holiday.name}</Text> : null}{uniqueImportantDayLabels(holiday).map((message) => <Text key={message} style={styles.todoNotificationTitle}>{message}</Text>)}{items.length ? items.map((item) => { const status = TODO_STATUS[item.status] ?? TODO_STATUS.pending; return <View key={item.id} style={[styles.todoItemCard, { backgroundColor: status.backgroundColor }]}><View style={styles.todoItemHeading}><Text style={styles.itemTitle}>{item.content}</Text><View style={styles.todoStatusTag}><Text style={styles.todoStatusText}>{status.label}</Text></View></View><Text style={styles.todoMeta}>{item.start_at ? `${dateOf(item.start_at)} ～ ${dateOf(item.due_at)}｜${new Date(item.start_at).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Taipei" })}` : new Date(item.due_at).toLocaleString("zh-TW", { timeZone: "Asia/Taipei" })}</Text></View>; }) : <Text style={styles.todoEmptyText}>這一天沒有待辦事項</Text>}</View>; })}</View>;
}

function BodyView({ data }: { data: BodyAnalytics }) {
  const weightGoal = data.goals.find((goal) => goal.goal_type === "weight")?.target_value ?? null;
  const exerciseGoal = data.goals.find((goal) => goal.goal_type === "exercise")?.target_value ?? null;
  const dietTooltip = (row: BodyAnalytics["diet"][number], nutrient: "fat_g" | "protein_g" | "carbs_g" | "calories", unit: string) => `${row.date}｜人工 ${row[`manual_${nutrient}`]} ${unit}｜AI ${row[`ai_${nutrient}`]} ${unit}｜合計 ${row[`total_${nutrient}`]} ${unit}`;
  const exerciseTooltip = (row: BodyAnalytics["exercise"][number]) => `${row.date}｜人工 ${row.manual_calories} 大卡｜AI ${row.ai_calories} 大卡｜合計 ${row.total_calories} 大卡`;
  return <>
    <ChartCard title="體重趨勢"><LineChart series={[{ label: "體重", color: "#2E9D74", marker: "solid", points: data.weight.map((row) => ({ label: row.date, value: row.weight })) }, { label: "目標", color: "#9AA8A4", marker: "hollow", points: data.weight.map((row) => ({ label: row.date, value: weightGoal })) }]} /></ChartCard>
    <ChartCard title="腰圍趨勢"><LineChart series={[{ label: "腰圍", color: "#D9544D", marker: "solid", points: data.weight.map((row) => ({ label: row.date, value: row.waist })) }]} /></ChartCard>
    <ChartCard title="BMI 趨勢"><LineChart series={[{ label: "BMI", color: "#3B82F6", marker: "solid", points: data.weight.map((row) => ({ label: row.date, value: row.bmi })) }]} /></ChartCard>
    <ChartCard title="飲食五大成分"><LineChart series={[
      { label: "飲水 ml（人工）", color: "#3B82F6", marker: "solid", points: data.diet.map((row) => ({ label: row.date, tooltip: `${row.date}｜飲水 ${row.water_ml} ml`, value: row.water_ml })) },
      ...([ ["脂肪", "fat_g", "#EB9741", "g"], ["蛋白質", "protein_g", "#2E9D74", "g"], ["碳水", "carbs_g", "#A56CC1", "g"], ["熱量", "calories", "#D9544D", "大卡"] ] as const).flatMap(([label, key, color, unit]) => [
        { label: `${label}（人工）`, color, marker: "solid" as const, points: data.diet.map((row) => ({ label: row.date, tooltip: dietTooltip(row, key, unit), value: row.manual_count ? row[`manual_${key}`] : null })) },
        { label: `${label}（AI）`, color, marker: "hollow" as const, points: data.diet.map((row) => ({ label: row.date, tooltip: dietTooltip(row, key, unit), value: row.ai_count ? row[`ai_${key}`] : null })) },
      ]),
    ]} /><Text style={styles.aiEstimateNotice}>提醒：實心圓為人工輸入，空心圓為 AI 估算；AI 結果未必是最準確的數值喔！</Text></ChartCard>
    <ChartCard title="運動趨勢"><LineChart series={[
      { label: "消耗大卡（人工）", color: "#EB9741", marker: "solid", points: data.exercise.map((row) => ({ label: row.date, tooltip: exerciseTooltip(row), value: row.manual_count ? row.manual_calories : null })) },
      { label: "消耗大卡（AI）", color: "#EB9741", marker: "hollow", points: data.exercise.map((row) => ({ label: row.date, tooltip: exerciseTooltip(row), value: row.ai_count ? row.ai_calories : null })) },
      { label: "分鐘", color: "#2E9D74", marker: "solid", points: data.exercise.map((row) => ({ label: row.date, value: row.minutes })) },
      { label: "目標分鐘", color: "#9AA8A4", marker: "hollow", points: data.exercise.map((row) => ({ label: row.date, value: exerciseGoal })) },
    ]} /><Text style={styles.aiEstimateNotice}>提醒：實心圓為人工輸入，空心圓為 AI 估算；AI 結果未必是最準確的數值喔！</Text></ChartCard>
  </>;
}

function FinanceView({ data }: { data: FinanceAnalytics }) {
  return <><View style={styles.metricRow}><Metric label="支出合計" sensitive value={`$${data.expense_total.toLocaleString()}`} /><Metric label="收入合計" sensitive value={`$${data.income_total.toLocaleString()}`} /></View><ChartCard title="支出趨勢"><LineChart series={[{ label: "每日支出", color: "#EB9741", points: data.daily.map((row) => ({ label: row.date, value: row.expense })) }]} /></ChartCard><ChartCard title="支出分類"><PieChart data={data.expense_categories} sensitive /></ChartCard><ChartCard title="收支比較"><LineChart series={[{ label: "收入", color: "#2E9D74", points: data.daily.map((row) => ({ label: row.date, value: row.income })) }, { label: "支出", color: "#EB9741", points: data.daily.map((row) => ({ label: row.date, value: row.expense })) }]} /></ChartCard></>;
}

function MoodView({ data }: { data: MoodAnalytics }) {
  return <><ChartCard title="心情趨勢"><LineChart series={[{ label: "心情分數", color: "#A56CC1", points: data.items.map((row) => ({ label: row.date, value: MOOD_SCORE[row.mood_category] ?? null })) }]} /></ChartCard><Section title="心情小記">{data.items.slice().reverse().map((item) => <View key={item.id} style={styles.listCard}><Text style={styles.itemTitle}>{MOOD_LABEL[item.mood_category] ?? item.mood_category}</Text><Text style={styles.meta}>{item.date}</Text><Text style={styles.bodyText}>{item.content}</Text>{item.achievement_note ? <Text style={styles.achievement}>✨ {item.achievement_note}</Text> : null}</View>)}</Section></>;
}

function JobsView({ data }: { data: JobsAnalytics }) {
  return <><ChartCard title="應徵漏斗"><FunnelChart data={[{ label: "已應徵", value: data.funnel.applied ?? 0 }, { label: "面試", value: data.funnel.interview ?? 0 }, { label: "Offer", value: data.funnel.offer ?? 0 }, { label: "未錄取／婉拒", value: data.funnel.rejected ?? 0 }]} /></ChartCard><ChartCard title="契合度分布"><BarChart color="#7656C9" data={[{ label: "80-100", value: data.score_distribution.high ?? 0 }, { label: "60-79", value: data.score_distribution.medium ?? 0 }, { label: "<60", value: data.score_distribution.low ?? 0 }]} /></ChartCard><Section title="本期 Top 推薦">{data.recommendations.map((item, index) => <View key={String(item.job_id_104 ?? index)} style={styles.listCard}><Text style={styles.itemTitle}>{String(item.title ?? "未命名職缺")} · {String(item.match_score ?? "—")} 分</Text><Text style={styles.bodyText}>{String(item.recommend_reason ?? "尚無推薦理由")}</Text><Text style={styles.meta}>{String(item.skill_gap_note ?? "尚無技能缺口資料")}</Text></View>)}</Section><Section title="應徵歷程">{data.timeline.map((item, index) => <View key={index} style={styles.timeline}><View style={styles.timelineDot} /><View style={styles.flex}><Text style={styles.itemTitle}>{String(item.title ?? "職缺")}</Text><Text style={styles.meta}>{String(item.created_at ?? "")} · {String(item.status ?? "")}</Text></View></View>)}</Section></>;
}

function ExamsView({ data }: { data: ExamsAnalytics }) {
  const accuracy = data.practice.map((row) => ({ label: String(row.date ?? ""), value: Number(row.total ?? 0) ? Math.round((Number(row.correct ?? 0) / Number(row.total)) * 100) : 0 }));
  const weak = Object.values(data.practice.reduce<Record<string, { label: string; total: number; wrong: number }>>((result, row) => { const key = String(row.question_type ?? "其他"); const current = result[key] ?? { label: key, total: 0, wrong: 0 }; current.total += Number(row.total ?? 0); current.wrong += Number(row.total ?? 0) - Number(row.correct ?? 0); result[key] = current; return result; }, {}));
  return <><Section title="證照目標">{data.goals.map((goal, index) => <View key={index} style={styles.listCard}><Text style={styles.itemTitle}>{String(goal.exam_type ?? "證照")}</Text><View style={styles.inlineSensitive}><Text style={styles.bodyText}>目標：</Text>{goal.target_score == null ? <Text style={styles.bodyText}>未設定</Text> : <SensitiveValue style={styles.bodyText}>{String(goal.target_score)}</SensitiveValue>}<Text style={styles.bodyText}>　日期：{String(goal.target_date ?? "未設定")}</Text></View></View>)}</Section><ChartCard title="每日練習正確率"><LineChart series={[{ label: "正確率 %", color: "#D89B20", points: accuracy }]} /></ChartCard><ChartCard title="弱點分析"><BarChart color="#D9544D" data={weak.map((item) => ({ label: item.label, value: item.wrong }))} /></ChartCard><Section title="正式成績歷程">{data.official_scores.map((score, index) => <View key={index} style={styles.listCard}><View style={styles.inlineSensitive}><Text style={styles.itemTitle}>{String(score.exam_type ?? "證照")} · </Text><SensitiveValue style={styles.itemTitle}>{String(score.score ?? "—")}</SensitiveValue></View><Text style={styles.meta}>{String(score.exam_date ?? "")}</Text>{score.note ? <Text style={styles.bodyText}>{String(score.note)}</Text> : null}</View>)}</Section></>;
}

function SkillsView({ data }: { data: SkillsAnalytics }) {
  return <><Section title="每日技術摘要">{data.digests.map((item, index) => <View key={index} style={styles.listCard}><Text style={styles.itemTitle}>{item.source?.toUpperCase() ?? "技術摘要"}</Text><Text style={styles.meta}>{item.digest_date}</Text><Text style={styles.bodyText}>{item.summary_text ?? "今日無內容"}</Text></View>)}</Section><Section title="YouTube 技術情報">{data.videos.map((item, index) => <View key={index} style={styles.listCard}><Text style={styles.itemTitle}>{item.title ?? "舊資料未保存影片標題"}</Text><Text style={styles.meta}>{item.pushed_on} · {item.topic ?? "未分類"}</Text><Text style={styles.bodyText}>{item.recommend_reason ?? "舊資料未保存推薦理由"}</Text></View>)}</Section></>;
}

function Section({ children, title }: { children: React.ReactNode; title: string }) { return <View style={styles.section}><Text style={styles.sectionTitle}>{title}</Text>{children}</View>; }
function Metric({ label, sensitive = false, value }: { label: string; sensitive?: boolean; value: string }) { return <View style={styles.metric}><Text style={styles.metricLabel}>{label}</Text>{sensitive ? <SensitiveValue style={styles.metricValue}>{value}</SensitiveValue> : <Text style={styles.metricValue}>{value}</Text>}</View>; }

const styles = StyleSheet.create({
  errorCard: { backgroundColor: "#FFF0F0", borderRadius: 14, gap: 7, padding: 16 }, errorText: { color: "#A33D3D" }, retry: { color: colors.primary, fontWeight: "800" },
  empty: { alignItems: "center", gap: 12, justifyContent: "center", minHeight: 240 }, emptyText: { color: colors.textMuted, fontSize: 15, fontWeight: "700" }, aiEstimateNotice: { color: colors.accent, fontSize: 13, fontWeight: "800", lineHeight: 20, textAlign: "center" },
  section: { gap: 10 }, sectionTitle: { color: colors.text, fontSize: 18, fontWeight: "900", marginTop: 5 },
  listCard: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 15, borderWidth: 1, gap: 6, padding: 15 }, itemTitle: { color: colors.text, fontSize: 15, fontWeight: "800" }, meta: { color: colors.textMuted, fontSize: 11 }, bodyText: { color: colors.text, fontSize: 13, lineHeight: 20 }, achievement: { color: "#8B5E16", fontSize: 12 },
  todoCalendarPage: { gap: 16 }, calendarCard: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 18, borderWidth: 1, overflow: "hidden", padding: 8 },
  calendarDay: { alignItems: "center", height: 82, justifyContent: "center", overflow: "hidden", width: "100%" }, calendarDayText: { color: colors.text, fontSize: 16 }, calendarDisabledText: { color: "#D6DEDC" }, calendarHolidayText: { color: colors.danger, fontWeight: "800" }, calendarHolidayName: { color: colors.danger, fontSize: 9, fontWeight: "700", lineHeight: 12, maxWidth: "100%" }, calendarHolidayPlaceholder: { height: 12 }, calendarRangeStart: { borderBottomLeftRadius: 24, borderTopLeftRadius: 24 }, calendarRangeEnd: { borderBottomRightRadius: 24, borderTopRightRadius: 24 }, calendarTodayInRange: { backgroundColor: colors.danger }, calendarTodayStandalone: { backgroundColor: colors.danger, borderRadius: 24 }, calendarTodayText: { color: colors.white, fontWeight: "900" }, todoCount: { fontSize: 11, fontWeight: "900", lineHeight: 14 }, todoCountPlaceholder: { height: 14 }, todoNotificationName: { color: IMPORTANT_DAY_COLOR, fontSize: 9, fontWeight: "800", lineHeight: 12, maxWidth: "100%" },
  todoDayCard: { backgroundColor: colors.surface, borderColor: "#1D2422", borderRadius: 15, borderWidth: 1, gap: 10, padding: 15 }, todoDayCardHighlighted: { borderColor: colors.danger, borderWidth: 4 }, todoDayTitle: { color: colors.text, fontSize: 18, fontWeight: "900" }, todoHolidayTitle: { color: colors.danger, fontSize: 13, fontWeight: "800" }, todoNotificationTitle: { color: IMPORTANT_DAY_COLOR, fontSize: 13, fontWeight: "800" }, todoItemCard: { borderColor: "#1D2422", borderRadius: 11, borderWidth: 1, gap: 7, padding: 12 }, todoItemHeading: { alignItems: "flex-start", flexDirection: "row", gap: 10, justifyContent: "space-between" }, todoStatusTag: { backgroundColor: "rgba(255,255,255,0.72)", borderColor: "#1D2422", borderRadius: 12, borderWidth: 1, paddingHorizontal: 9, paddingVertical: 3 }, todoStatusText: { color: colors.text, fontSize: 11, fontWeight: "900" }, todoMeta: { color: colors.text, fontSize: 11 }, todoEmptyText: { color: colors.textMuted, fontSize: 12 },
  metricRow: { flexDirection: "row", flexWrap: "wrap", gap: 12 }, metric: { backgroundColor: colors.surface, borderRadius: 15, flex: 1, minWidth: 150, padding: 17 }, metricLabel: { color: colors.textMuted, fontSize: 12 }, metricValue: { color: colors.text, fontSize: 24, fontWeight: "900", marginTop: 5 },
  timeline: { alignItems: "flex-start", flexDirection: "row", gap: 10, paddingVertical: 5 }, timelineDot: { backgroundColor: "#7656C9", borderRadius: 5, height: 10, marginTop: 5, width: 10 }, flex: { flex: 1 },
  savedToast: { alignItems: "center", alignSelf: "center", backgroundColor: colors.primaryDark, borderRadius: 20, bottom: 22, flexDirection: "row", gap: 14, paddingHorizontal: 18, paddingVertical: 10, position: "absolute", zIndex: 10 }, savedText: { color: colors.white, fontWeight: "700" }, undoText: { color: "#FFD18A", fontWeight: "900", textDecorationLine: "underline" },
  recordActions: { flexDirection: "row", gap: 8, justifyContent: "flex-end", marginTop: 6 }, recordButton: { borderRadius: 9, paddingHorizontal: 14, paddingVertical: 8 }, editButton: { backgroundColor: colors.primarySoft }, deleteButton: { backgroundColor: "#FAD7D5" }, recordButtonText: { color: colors.primaryDark, fontWeight: "800" }, deleteButtonText: { color: colors.danger, fontWeight: "800" }, telegramHint: { color: colors.textMuted, fontSize: 11, marginTop: 4 },
  bodyRecordValues: { gap: 6 }, bodyRecordValue: { color: colors.text, fontSize: 15, fontWeight: "700" }, inlineSensitive: { alignItems: "baseline", flexDirection: "row", flexWrap: "wrap" }, bodyGoalText: { borderTopColor: colors.border, borderTopWidth: 1, color: colors.primaryDark, fontSize: 13, fontWeight: "800", marginTop: 6, paddingTop: 10 },
  deleteBackdrop: { alignItems: "center", backgroundColor: "rgba(16,38,34,.45)", flex: 1, justifyContent: "center", padding: 20 }, deleteCard: { backgroundColor: colors.surface, borderRadius: 20, gap: 16, maxWidth: 420, padding: 24, width: "100%" }, deleteTitle: { color: colors.text, fontSize: 21, fontWeight: "900" },
});
