import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";
import { Redirect, useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Calendar, type DateData } from "react-native-calendars";
import { ActivityIndicator, Linking, Modal, ScrollView, StyleSheet, useWindowDimensions } from "react-native";

import { AppPressable as Pressable } from "@/components/AppPressable";
import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";
import { AppShell } from "@/components/AppShell";
import { GoalSummaryCard } from "@/components/AnalyticsShared";
import { BarChart, ChartCard, FunnelChart, LineChart } from "@/components/Charts";
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
  updateRecord,
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
const MOOD_LABEL: Record<string, string> = { angry_anxious: "😡 生氣／焦慮", sad_down: "😢 難過／低落", tired_burned_out: "🫠 疲憊／厭世", neutral: "🙂 普通／平淡", calm_relaxed: "😌 平靜／放鬆", happy_excited: "🥳 高興／興奮" };
type BodyTab = "weight" | "diet" | "exercise";
type JobTab = "overview" | "recommendations" | "applications";
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
  const [loading, setLoading] = useState(true);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ kind: RecordKind; item: RecordItem } | null>(null);
  const [deleting, setDeleting] = useState<{ kind: RecordKind; item: RecordItem } | null>(null);
  const [pendingDeletion, setPendingDeletion] = useState<{ kind: RecordKind; item: RecordItem } | null>(null);
  const [bodyTab, setBodyTab] = useState<BodyTab>("weight");
  const [examCertificate, setExamCertificate] = useState<string>("");
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
  const initialLoading = loading && !payload;
  const examData = module === "exams" && payload ? payload as ExamsAnalytics : null;
  const selectedExam = examData?.certificates.some((item) => item.key === examCertificate)
    ? examCertificate
    : examData?.certificates[0]?.key ?? "";

  return (
    <AppShell scrollViewRef={scrollViewRef} title={title}>
      {!error && examData ? <CertificateTabs certificates={examData.certificates} selected={selectedExam} onSelect={setExamCertificate} /> : null}
      {!error && payload ? <TopGoalSummary bodyTab={bodyTab} examCertificate={selectedExam} module={module} payload={payload} /> : null}
      {!error && module === "body" && payload ? <BodyTabs selected={bodyTab} onSelect={setBodyTab} /> : null}
      {!initialLoading && payload && (module === "skills" ? (
        <SingleDateFilter calendarDays={filterCalendarDays} date={skillDate} onCalendarMonthChange={setCalendarMonth} onApply={setSkillDate} />
      ) : (
        <DateRangeFilter
          allowFuture={module === "todos"}
          calendarCounts={module === "todos" ? (payload as TodoAnalytics | null)?.calendar_counts : undefined}
          calendarDays={module === "todos" ? (payload as TodoAnalytics | null)?.calendar_days : filterCalendarDays}
          holidayOnly={module !== "todos"}
          hint={module === "todos" ? "可查任意日期，每次區間最少 1 天、最多 7 天" : "可查任意歷史日期，每次區間最少 1 天、最多 30 天"}
          maxDays={module === "todos" ? 7 : undefined}
          minDays={1}
          onCalendarMonthChange={setCalendarMonth}
          onApply={setRange}
          range={range}
        />
      ))}
      {initialLoading ? <View style={styles.initialLoading}><ActivityIndicator color={colors.primary} size="large" /><Text style={styles.emptyText}>資料載入中…</Text></View> : null}
      {error ? <View style={styles.errorCard}><Text style={styles.errorText}>{error}</Text><Pressable onPress={() => void load()}><Text style={styles.retry}>重新載入</Text></Pressable></View> : null}
      {!error && payload && !hasRangeData && module !== "todos" ? <EmptyState hasAnyData={hasAnyData} /> : null}
      {!error && payload ? renderModule(module, payload, range, calendarMonth, setCalendarMonth, scrollViewRef, bodyTab, selectedExam) : null}
      {!error && payload ? <EditableRecords bodyTab={bodyTab} module={module} onDelete={setDeleting} onEdit={setEditing} payload={payload} /> : null}
      {!error && module === "todos" && payload ? <OverdueTodos authorizedRequest={authorizedRequest} data={payload as TodoAnalytics} onEdit={(item) => setEditing({ kind: "todo", item: item as unknown as RecordItem })} onSaved={load} /> : null}
      {savedMessage ? <View style={styles.savedToast}><Text style={styles.savedText}>{savedMessage}</Text>{pendingDeletion ? <Pressable onPress={undoDelete}><Text style={styles.undoText}>復原</Text></Pressable> : null}</View> : null}
      {editing ? <RecordModal authorizedRequest={authorizedRequest} initial={editing.item} kind={editing.kind} onClose={() => setEditing(null)} onSaved={async () => { await load(); setSavedMessage("紀錄已更新"); setTimeout(() => setSavedMessage(null), 2400); }} visible /> : null}
      <Modal animationType="fade" onRequestClose={() => setDeleting(null)} transparent visible={Boolean(deleting)}><View style={styles.deleteBackdrop}><View style={styles.deleteCard}><Text style={styles.deleteTitle}>確認刪除？</Text><Text style={styles.bodyText}>確認後有 5 秒可復原，逾時才會正式刪除。</Text><View style={styles.recordActions}><Pressable onPress={() => setDeleting(null)} style={[styles.recordButton, styles.editButton]}><Text style={styles.recordButtonText}>取消</Text></Pressable><Pressable disabled={Boolean(pendingDeletion)} onPress={scheduleDelete} style={[styles.recordButton, styles.deleteButton]}><Text style={styles.deleteButtonText}>刪除</Text></Pressable></View></View></View></Modal>
    </AppShell>
  );
}

function EditableRecords({ bodyTab, module, onDelete, onEdit, payload }: { bodyTab: BodyTab; module: AnalyticsModule; onDelete: (value: { kind: RecordKind; item: RecordItem }) => void; onEdit: (value: { kind: RecordKind; item: RecordItem }) => void; payload: AnalyticsResponseMap[AnalyticsModule] }) {
  const { height: windowHeight } = useWindowDimensions();
  let groups: Array<{ kind: RecordKind; label: string; records: RecordItem[]; latest?: RecordItem | null }> = [];
  if (module === "todos") groups = [{ kind: "todo", label: "待辦紀錄管理", records: (payload as TodoAnalytics).items as unknown as RecordItem[] }];
  if (module === "finance") { const value = payload as FinanceAnalytics; groups = [{ kind: "finance", label: "日期區間收支紀錄", records: value.records, latest: value.latest_record }]; }
  if (module === "mood") { const value = payload as MoodAnalytics; groups = [{ kind: "mood", label: "日期區間心情小記", records: value.items as unknown as RecordItem[], latest: value.latest_record }]; }
  if (module === "body") { const value = payload as BodyAnalytics; const config = { weight: { label: "日期區間體態紀錄", records: value.weight_records, latest: value.latest_records.weight }, diet: { label: "日期區間飲食紀錄", records: value.diet_records, latest: value.latest_records.diet }, exercise: { label: "日期區間運動紀錄", records: value.exercise_records, latest: value.latest_records.exercise } }[bodyTab]; groups = [{ kind: bodyTab, ...config }]; }
  if (!groups.length) return null;
  const recordCard = (group: typeof groups[number], item: RecordItem, latest: boolean) => <View key={`${group.kind}-${item.id}-${latest ? "latest" : "range"}`} style={styles.listCard}>{group.kind === "weight" ? <View style={styles.bodyRecordValues}><SensitiveRow label="身高" value={item.height_cm == null ? null : `${Number(item.height_cm).toFixed(1)} 公分`} /><SensitiveRow label="體重" value={item.weight_kg == null ? null : `${Number(item.weight_kg).toFixed(1)} 公斤`} /><SensitiveRow label="腰圍" value={item.waist_cm == null ? null : `${Number(item.waist_cm).toFixed(1)} 公分`} /><SensitiveRow label="BMI" unavailable="無法計算" value={item.bmi == null ? null : Number(item.bmi).toFixed(2)} /></View> : group.kind === "finance" ? <View style={styles.inlineSensitive}><Text style={styles.itemTitle}>{item.type === "income" ? "收入" : "支出"}｜{String(item.category)}｜</Text><SensitiveValue style={styles.itemTitle}>{`${Number(item.amount).toLocaleString()} 元`}</SensitiveValue></View> : <Text style={styles.itemTitle}>{recordSummary(group.kind, item)}</Text>}<Text style={styles.meta}>{String(item.date ?? item.entry_date ?? item.due_at ?? "")}</Text>{latest && item.can_edit ? <View style={styles.recordActions}><Pressable onPress={() => onEdit({ kind: group.kind, item })} style={[styles.recordButton, styles.editButton]}><Text style={styles.recordButtonText}>編輯</Text></Pressable><Pressable onPress={() => onDelete({ kind: group.kind, item })} style={[styles.recordButton, styles.deleteButton]}><Text style={styles.deleteButtonText}>刪除</Text></Pressable></View> : latest ? <Text style={styles.telegramHint}>歷史紀錄請至 Telegram 管理。</Text> : null}</View>;
  return <>{groups.map((group) => <View key={group.kind} style={styles.recordGroup}><Section title={group.label}><ScrollView contentContainerStyle={styles.rangeRecordContent} nestedScrollEnabled style={{ maxHeight: windowHeight * 0.6 }}>{group.records.length ? group.records.map((item) => recordCard(group, item, false)) : <Text style={styles.todoEmptyText}>這段期間沒有紀錄</Text>}</ScrollView></Section>{group.latest !== undefined ? <Section title="最近紀錄">{group.latest ? recordCard(group, group.latest, true) : <Text style={styles.todoEmptyText}>尚無紀錄</Text>}</Section> : null}</View>)}</>;
}

function OverdueTodos({ authorizedRequest, data, onEdit, onSaved }: { authorizedRequest: Parameters<typeof updateRecord>[0]; data: TodoAnalytics; onEdit: (item: TodoAnalytics["overdue_items"][number]) => void; onSaved: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const changeStatus = async (item: TodoAnalytics["overdue_items"][number], nextStatus: "completed" | "cancelled") => {
    setBusy(item.id);
    setActionError(null);
    try {
      await updateRecord(authorizedRequest, "todo", item.id, {
        content: item.content,
        start_at: item.start_at ?? item.due_at,
        due_at: item.due_at,
        status: nextStatus,
      });
      await onSaved();
    } catch (requestError) {
      setActionError(requestError instanceof ApiError ? requestError.message : "待辦更新失敗，請稍後再試");
    } finally {
      setBusy(null);
    }
  };
  return <>
    <Pressable onPress={() => setOpen(true)} style={styles.overdueEntry}><Text style={styles.overdueEntryText}>逾期待辦（{data.overdue_count}）</Text><MaterialCommunityIcons color={colors.danger} name="chevron-right" size={22} /></Pressable>
    <Modal animationType="fade" onRequestClose={() => setOpen(false)} transparent visible={open}><View style={styles.deleteBackdrop}><View style={styles.overdueModal}><View style={styles.todoItemHeading}><Text style={styles.deleteTitle}>逾期待辦</Text><Pressable onPress={() => setOpen(false)}><Text style={styles.retry}>關閉</Text></Pressable></View>{actionError ? <Text style={styles.errorText}>{actionError}</Text> : null}<ScrollView contentContainerStyle={styles.overdueList}>{data.overdue_items.length ? data.overdue_items.map((item) => <View key={item.id} style={styles.listCard}><Text style={styles.itemTitle}>{item.content}</Text><Text style={styles.meta}>{item.due_at}</Text><View style={styles.recordActions}><Pressable disabled={busy === item.id} onPress={() => void changeStatus(item, "completed")} style={[styles.recordButton, styles.editButton]}><Text style={styles.recordButtonText}>標記完成</Text></Pressable><Pressable onPress={() => { setOpen(false); onEdit(item); }} style={[styles.recordButton, styles.editButton]}><Text style={styles.recordButtonText}>編輯期限</Text></Pressable><Pressable disabled={busy === item.id} onPress={() => void changeStatus(item, "cancelled")} style={[styles.recordButton, styles.deleteButton]}><Text style={styles.deleteButtonText}>取消待辦</Text></Pressable></View></View>) : <Text style={styles.todoEmptyText}>目前沒有逾期待辦</Text>}</ScrollView></View></View></Modal>
  </>;
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
  bodyTab: BodyTab,
  examCertificate: string,
) {
  switch (module) {
    case "todos": return <TodoView calendarMonth={calendarMonth} data={payload as TodoAnalytics} range={range} scrollViewRef={scrollViewRef} setCalendarMonth={setCalendarMonth} />;
    case "body": return <BodyView data={payload as BodyAnalytics} selected={bodyTab} />;
    case "finance": return <FinanceView data={payload as FinanceAnalytics} />;
    case "mood": return <MoodView data={payload as MoodAnalytics} />;
    case "jobs": return <JobsView data={payload as JobsAnalytics} />;
    case "exams": return <ExamsView certificate={examCertificate} data={payload as ExamsAnalytics} />;
    case "skills": return <SkillsView data={payload as SkillsAnalytics} />;
  }
}

function selectGoal(goals: BodyAnalytics["goals"], type: BodyTab) {
  const active = goals.filter((goal) => goal.goal_type === type && goal.status === "active");
  const dated = active.filter((goal) => goal.target_date);
  return (dated.length ? dated : active).slice().sort((left, right) => {
    if (dated.length) {
      const byDate = String(left.target_date).localeCompare(String(right.target_date));
      if (byDate) return byDate;
    }
    return String(right.updated_at ?? "").localeCompare(String(left.updated_at ?? ""));
  })[0] ?? null;
}

function TopGoalSummary({ bodyTab, examCertificate, module, payload }: { bodyTab: BodyTab; examCertificate: string; module: AnalyticsModule; payload: AnalyticsResponseMap[AnalyticsModule] }) {
  if (module === "body") {
    const data = payload as BodyAnalytics;
    const goals = data.goals.filter((goal) => goal.goal_type === bodyTab);
    return <GoalSummaryCard goal={selectGoal(data.goals, bodyTab)} goals={goals} />;
  }
  if (module === "finance") {
    const data = payload as FinanceAnalytics;
    return <GoalSummaryCard goal={data.goal_summary} goals={data.goals} />;
  }
  if (module === "exams") {
    const data = payload as ExamsAnalytics;
    const goals = data.goals.filter((goal) => String(goal.goal_type).toLowerCase() === examCertificate);
    return <GoalSummaryCard goal={data.goal_summaries[examCertificate] ?? null} goals={goals} />;
  }
  return null;
}

function BodyTabs({ onSelect, selected }: { onSelect: (value: BodyTab) => void; selected: BodyTab }) {
  const tabs: Array<{ key: BodyTab; label: string }> = [{ key: "weight", label: "體態" }, { key: "diet", label: "飲食" }, { key: "exercise", label: "運動" }];
  return <View style={styles.tabs}>{tabs.map((tab) => <Pressable key={tab.key} onPress={() => onSelect(tab.key)} style={[styles.tab, selected === tab.key && styles.tabSelected]}><Text style={[styles.tabText, selected === tab.key && styles.tabTextSelected]}>{tab.label}</Text></Pressable>)}</View>;
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

function BodyView({ data, selected }: { data: BodyAnalytics; selected: BodyTab }) {
  const weightGoal = data.goals.find((goal) => goal.goal_type === "weight")?.target_value ?? null;
  const exerciseGoal = data.goals.find((goal) => goal.goal_type === "exercise")?.target_value ?? null;
  const dietTooltip = (row: BodyAnalytics["diet"][number], nutrient: "fat_g" | "protein_g" | "carbs_g" | "calories", unit: string) => `${row.date}｜人工 ${row[`manual_${nutrient}`]} ${unit}｜AI ${row[`ai_${nutrient}`]} ${unit}｜合計 ${row[`total_${nutrient}`]} ${unit}`;
  const exerciseTooltip = (row: BodyAnalytics["exercise"][number]) => `${row.date}｜人工 ${row.manual_calories} 大卡｜AI ${row.ai_calories} 大卡｜合計 ${row.total_calories} 大卡`;
  if (selected === "weight") return <>
    <ChartCard title="體重趨勢"><LineChart yAxisLabel="體重(公斤)" series={[{ label: "體重", color: "#2E9D74", marker: "solid", points: data.weight.map((row) => ({ label: row.date, value: row.weight })) }, { label: "目標", color: "#9AA8A4", marker: "hollow", points: data.weight.map((row) => ({ label: row.date, value: weightGoal })) }]} /></ChartCard>
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
    <ChartCard title="運動時間趨勢"><LineChart yAxisLabel="時間(分鐘)" series={[{ label: "分鐘", color: "#2E9D74", marker: "solid", points: data.exercise.map((row) => ({ label: row.date, value: row.minutes })) }, { label: "目標分鐘", color: "#9AA8A4", marker: "hollow", points: data.exercise.map((row) => ({ label: row.date, value: exerciseGoal })) }]} zeroBased /></ChartCard>
    <ChartCard title="運動消耗趨勢"><LineChart yAxisLabel="熱量(大卡)" series={[
      { label: "消耗大卡（人工）", color: "#EB9741", marker: "solid", points: data.exercise.map((row) => ({ label: row.date, tooltip: exerciseTooltip(row), value: row.manual_count ? row.manual_calories : null })) },
      { label: "消耗大卡（AI）", color: "#EB9741", marker: "hollow", points: data.exercise.map((row) => ({ label: row.date, tooltip: exerciseTooltip(row), value: row.ai_count ? row.ai_calories : null })) },
    ]} zeroBased /><Text style={styles.aiEstimateNotice}>提醒：實心圓為人工輸入，空心圓為 AI 估算；AI 結果未必是最準確的數值喔！</Text></ChartCard>
  </>;
}

function FinanceView({ data }: { data: FinanceAnalytics }) {
  return <><View style={styles.metricRow}><Metric label="收入合計" sensitive value={`${data.income_total.toLocaleString()} 元`} /><Metric label="支出合計" sensitive value={`${data.expense_total.toLocaleString()} 元`} /><Metric label="結餘" sensitive value={`${(data.income_total - data.expense_total).toLocaleString()} 元`} /></View><ChartCard title="收支比較"><LineChart yAxisLabel="台幣金額(元)" zeroBased series={[{ label: "收入", color: "#2E9D74", points: data.daily.map((row) => ({ label: row.date, value: row.income })) }, { label: "支出", color: "#EB9741", points: data.daily.map((row) => ({ label: row.date, value: row.expense })) }]} /></ChartCard></>;
}

function MoodView({ data: _data }: { data: MoodAnalytics }) { return null; }

function JobsView({ data }: { data: JobsAnalytics }) {
  const [selected, setSelected] = useState<JobTab>("overview");
  return <>
    <View style={styles.tabs}>{([ ["overview", "總覽"], ["recommendations", "推薦職缺"], ["applications", "應徵紀錄"] ] as const).map(([key, label]) => <Pressable key={key} onPress={() => setSelected(key)} style={[styles.tab, selected === key && styles.tabSelected]}><Text style={[styles.tabText, selected === key && styles.tabTextSelected]}>{label}</Text></Pressable>)}</View>
    {selected === "overview" ? <><View style={styles.metricRow}><Metric label="本期推薦" value={`${data.recommendations.length} 筆`} /><Metric label="面試中" value={`${data.funnel.interview ?? 0} 筆`} /><Metric label="Offer" value={`${data.funnel.offer ?? 0} 筆`} /></View><ChartCard title="應徵漏斗"><FunnelChart data={[{ label: "已應徵", value: data.funnel.applied ?? 0 }, { label: "面試", value: data.funnel.interview ?? 0 }, { label: "Offer", value: data.funnel.offer ?? 0 }, { label: "未錄取／婉拒", value: data.funnel.rejected ?? 0 }]} /></ChartCard><ChartCard title="契合度分布"><BarChart color="#7656C9" data={[{ label: "80-100", value: data.score_distribution.high ?? 0 }, { label: "60-79", value: data.score_distribution.medium ?? 0 }, { label: "<60", value: data.score_distribution.low ?? 0 }]} xAxisLabel="契合度區間" yAxisLabel="職缺數量(筆)" /></ChartCard></> : null}
    {selected === "recommendations" ? <Section title="推薦職缺">{data.recommendations.length ? data.recommendations.map((item, index) => <View key={String(item.job_id_104 ?? index)} style={styles.listCard}><Text style={styles.itemTitle}>{String(item.title ?? "未命名職缺")} · {String(item.match_score ?? "—")} 分</Text><Text style={styles.meta}>{[item.company_name, item.region, item.source].filter(Boolean).map(String).join("｜")}</Text><Text style={styles.bodyText}>{String(item.recommend_reason ?? "尚無推薦理由")}</Text><Text style={styles.meta}>{String(item.skill_gap_note ?? "尚無技能缺口資料")}</Text>{item.url ? <Pressable onPress={() => void Linking.openURL(String(item.url))}><Text style={styles.retry}>查看職缺</Text></Pressable> : null}</View>) : <Text style={styles.todoEmptyText}>這段期間沒有推薦職缺</Text>}</Section> : null}
    {selected === "applications" ? <Section title="應徵紀錄">{data.timeline.length ? data.timeline.map((item, index) => <View key={`${String(item.job_id_104)}-${String(item.created_at)}-${index}`} style={styles.timeline}><View style={styles.timelineDot} /><View style={styles.flex}><Text style={styles.itemTitle}>{String(item.title ?? "職缺")}</Text><Text style={styles.meta}>{String(item.created_at ?? "")} · {jobStatusLabel(String(item.status ?? ""))}</Text></View></View>) : <Text style={styles.todoEmptyText}>這段期間沒有應徵紀錄</Text>}</Section> : null}
    <Text style={styles.telegramHint}>履歷、條件、關鍵字與職缺狀態請前往 Telegram「求職設定」管理。</Text>
  </>;
}

function CertificateTabs({ certificates, onSelect, selected }: { certificates: ExamsAnalytics["certificates"]; onSelect: (key: string) => void; selected: string }) {
  if (!certificates.length) return <View style={styles.listCard}><Text style={styles.itemTitle}>尚未建立證照</Text><Text style={styles.telegramHint}>請前往 Telegram「考試設定」新增證照。</Text></View>;
  return <ScrollView contentContainerStyle={styles.certificateTabs} horizontal showsHorizontalScrollIndicator={false}>{certificates.map((item) => <Pressable key={item.key} onPress={() => onSelect(item.key)} style={[styles.certificateTab, selected === item.key && styles.certificateTabSelected]}><Text style={[styles.tabText, selected === item.key && styles.tabTextSelected]}>{item.display_name}</Text></Pressable>)}</ScrollView>;
}

function ExamsView({ certificate, data }: { certificate: string; data: ExamsAnalytics }) {
  const profile = data.certificates.find((item) => item.key === certificate);
  const practice = data.practice.filter((row) => String(row.exam_type ?? "").toLowerCase() === certificate);
  const daily = Object.values(practice.reduce<Record<string, { label: string; total: number; correct: number }>>((result, row) => { const key = String(row.date ?? ""); const current = result[key] ?? { label: key, total: 0, correct: 0 }; current.total += Number(row.total ?? 0); current.correct += Number(row.correct ?? 0); result[key] = current; return result; }, {})).sort((left, right) => left.label.localeCompare(right.label));
  const accuracy = daily.map((row) => ({ label: row.label, value: row.total ? Math.round((row.correct / row.total) * 100) : 0 }));
  const weak = Object.values(practice.reduce<Record<string, { label: string; wrong: number }>>((result, row) => { const key = String(row.question_type ?? "其他"); const current = result[key] ?? { label: key, wrong: 0 }; current.wrong += Number(row.total ?? 0) - Number(row.correct ?? 0); result[key] = current; return result; }, {}));
  const scores = data.official_scores.filter((row) => String(row.exam_type ?? "").toLowerCase() === certificate);
  if (!profile) return <Text style={styles.todoEmptyText}>尚無可查看的證照資料</Text>;
  return <>
    {profile.has_question_bank ? <>{practice.length ? <><View style={styles.metricRow}><Metric label="作答題數" value={`${daily.reduce((sum, row) => sum + row.total, 0)} 題`} /><Metric label="平均正確率" value={`${daily.reduce((sum, row) => sum + row.total, 0) ? Math.round(daily.reduce((sum, row) => sum + row.correct, 0) / daily.reduce((sum, row) => sum + row.total, 0) * 100) : 0}%`} /></View><ChartCard title="每日練習正確率"><LineChart yAxisLabel="正確率(%)" zeroBased series={[{ label: "正確率 %", color: "#D89B20", points: accuracy }]} /></ChartCard><ChartCard title="弱點分析"><BarChart color="#D9544D" data={weak.map((item) => ({ label: item.label, value: item.wrong }))} xAxisLabel="題型" yAxisLabel="錯題數(題)" /></ChartCard></> : <Text style={styles.todoEmptyText}>這段期間沒有練習紀錄</Text>}</> : <View style={styles.listCard}><Text style={styles.itemTitle}>{profile.display_name} 尚未建立題庫</Text><Text style={styles.bodyText}>目前可查看目標與正式成績，題庫功能將於後續開發。</Text></View>}
    <Section title="正式成績">{scores.length ? scores.map((score, index) => <View key={`${String(score.exam_date)}-${index}`} style={styles.listCard}><SensitiveValue style={styles.itemTitle}>{String(score.score ?? "—")}</SensitiveValue><Text style={styles.meta}>{String(score.exam_date ?? "")}</Text>{score.note ? <Text style={styles.bodyText}>{String(score.note)}</Text> : null}</View>) : <Text style={styles.todoEmptyText}>這段期間沒有正式成績</Text>}</Section>
    <Text style={styles.telegramHint}>證照、目標、每日題數與正式成績請前往 Telegram「考試設定」管理。</Text>
  </>;
}

function jobStatusLabel(status: string): string { return ({ applied: "已應徵", interview: "面試", offer: "Offer", rejected: "未錄取／婉拒" } as Record<string, string>)[status] ?? status; }

function SkillsView({ data }: { data: SkillsAnalytics }) {
  return <><Section title="每日技術摘要">{data.digests.map((item, index) => <View key={index} style={styles.listCard}><Text style={styles.itemTitle}>{item.source?.toUpperCase() ?? "技術摘要"}</Text><Text style={styles.meta}>{item.digest_date}</Text><Text style={styles.bodyText}>{item.summary_text ?? "今日無內容"}</Text></View>)}</Section><Section title="YouTube 技術情報">{data.videos.map((item, index) => <View key={index} style={styles.listCard}><Text style={styles.itemTitle}>{item.title ?? "舊資料未保存影片標題"}</Text><Text style={styles.meta}>{item.pushed_on} · {item.topic ?? "未分類"}</Text><Text style={styles.bodyText}>{item.recommend_reason ?? "舊資料未保存推薦理由"}</Text></View>)}</Section></>;
}

function Section({ children, title }: { children: React.ReactNode; title: string }) { return <View style={styles.section}><Text style={styles.sectionTitle}>{title}</Text>{children}</View>; }
function Metric({ label, sensitive = false, value }: { label: string; sensitive?: boolean; value: string }) { return <View style={styles.metric}><Text style={styles.metricLabel}>{label}</Text>{sensitive ? <SensitiveValue style={styles.metricValue}>{value}</SensitiveValue> : <Text style={styles.metricValue}>{value}</Text>}</View>; }

const styles = StyleSheet.create({
  initialLoading: { alignItems: "center", gap: 12, justifyContent: "center", minHeight: 360 },
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
  tabs: { backgroundColor: colors.border, borderRadius: 12, flexDirection: "row", overflow: "hidden" }, tab: { alignItems: "center", flex: 1, paddingVertical: 11 }, tabSelected: { backgroundColor: colors.primarySoft }, tabText: { color: colors.textMuted, fontSize: 15, fontWeight: "800" }, tabTextSelected: { color: colors.primaryDark },
  certificateTabs: { gap: 8 }, certificateTab: { backgroundColor: colors.border, borderRadius: 18, paddingHorizontal: 18, paddingVertical: 10 }, certificateTabSelected: { backgroundColor: colors.primarySoft },
  rangeRecordContent: { gap: 10 }, recordGroup: { gap: 14 },
  deleteBackdrop: { alignItems: "center", backgroundColor: "rgba(16,38,34,.45)", flex: 1, justifyContent: "center", padding: 20 }, deleteCard: { backgroundColor: colors.surface, borderRadius: 20, gap: 16, maxWidth: 420, padding: 24, width: "100%" }, deleteTitle: { color: colors.text, fontSize: 21, fontWeight: "900" },
  overdueEntry: { alignItems: "center", backgroundColor: "#FFF0F0", borderColor: "#F0B9B5", borderRadius: 14, borderWidth: 1, flexDirection: "row", justifyContent: "space-between", padding: 15 }, overdueEntryText: { color: colors.danger, fontSize: 16, fontWeight: "900" }, overdueList: { gap: 10 }, overdueModal: { backgroundColor: colors.surface, borderRadius: 20, gap: 14, maxHeight: "80%", maxWidth: 520, padding: 20, width: "100%" },
});
