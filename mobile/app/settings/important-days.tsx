import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";
import { Redirect } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Calendar, type DateData } from "react-native-calendars";
import { ActivityIndicator, Alert, Modal, ScrollView, StyleSheet, Switch, TextInput } from "react-native";

import { AppPressable as Pressable } from "@/components/AppPressable";
import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";
import { AppShell } from "@/components/AppShell";
import { TimePickerField } from "@/components/TimePickerField";
import { todayIsoDate } from "@/components/DateRangeFilter";
import { useAppPreferences } from "@/context/AppPreferencesContext";
import { useAuth } from "@/context/AuthContext";
import {
  createImportantDay,
  deleteImportantDay,
  getAnalytics,
  getImportantDays,
  updateImportantDay,
  type ImportantDay,
  type ImportantDayUser,
  type TodoAnalytics,
} from "@/services/analyticsApi";
import { IMPORTANT_DAY_COLOR, uniqueImportantDayLabels } from "@/utils/calendarLabels";

const RECURRENCE = [
  ["fixed_annual", "每年固定"], ["flexible_annual", "每年另訂"], ["one_time", "一次性"],
] as const;
const AUDIENCE = [["self", "僅自己"], ["specific", "指定家人"], ["all", "全部家人"]] as const;
const REMINDERS = [[0, "當天"], [1, "提前 1 天"], [3, "提前 3 天"], [7, "提前 7 天"]] as const;

type Filter = "upcoming" | "fixed_annual" | "flexible_annual" | "one_time" | "inactive";

export default function ImportantDaysScreen() {
  const { authorizedRequest, status, user } = useAuth();
  const { colors, theme } = useAppPreferences();
  const styles = createStyles(colors, theme);
  const [items, setItems] = useState<ImportantDay[]>([]);
  const [users, setUsers] = useState<ImportantDayUser[]>([]);
  const [filter, setFilter] = useState<Filter>("upcoming");
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [operationMessage, setOperationMessage] = useState<string | null>(null);
  const [editing, setEditing] = useState<ImportantDay | null | undefined>(undefined);
  const [pendingDeletion, setPendingDeletion] = useState<ImportantDay | null>(null);
  const deleteTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    if (status !== "authenticated") return;
    setLoading(true); setMessage(null);
    try { const result = await getImportantDays(authorizedRequest); setItems(result.items); setUsers(result.users); }
    catch (error) { setMessage(error instanceof Error && error.message !== "目前無法連線，請確認網路後再試" ? error.message : "目前無法連接資料服務，請稍後再試"); }
    finally { setLoading(false); }
  }, [authorizedRequest, status]);
  useEffect(() => { void load(); }, [load]);

  const scheduleDelete = (item: ImportantDay) => {
    if (pendingDeletion) return;
    setPendingDeletion(item); setOperationMessage("已排定刪除，5 秒內可復原");
    deleteTimer.current = setTimeout(() => {
      void deleteImportantDay(authorizedRequest, item.id)
        .then(async (result) => { setPendingDeletion(null); setOperationMessage(result.message); await load(); })
        .catch((error) => { setPendingDeletion(null); setMessage(error instanceof Error ? error.message : "刪除失敗，請重試"); });
    }, 5000);
  };

  const undoDelete = () => {
    if (deleteTimer.current) clearTimeout(deleteTimer.current);
    deleteTimer.current = null; setPendingDeletion(null); setOperationMessage("已復原，資料未刪除");
  };

  useEffect(() => {
    if (!operationMessage || pendingDeletion) return;
    const timer = setTimeout(() => setOperationMessage(null), 2400);
    return () => clearTimeout(timer);
  }, [operationMessage, pendingDeletion]);

  const visible = useMemo(() => items.filter((item) => {
    if (filter === "inactive") return !item.is_active;
    if (!item.is_active) return false;
    if (filter !== "upcoming") return item.recurrence_type === filter;
    return item.next_occurrence !== null || item.recurrence_type === "flexible_annual";
  }), [filter, items]);

  if (status === "guest") return <Redirect href="/login" />;
  return <AppShell title="重要日子設定">
    <View style={styles.intro}><MaterialCommunityIcons color={colors.primary} name="calendar-star" size={28} /><View style={styles.flex}><Text style={styles.introTitle}>管理重要日子</Text><Text style={styles.description}>待辦事項是唯一整合行事曆；此頁只負責事件、提醒與通知對象設定。</Text></View></View>
    <Pressable onPress={() => setEditing(null)} style={styles.addButton}><MaterialCommunityIcons color={theme === "dark" ? colors.background : colors.white} name="plus" size={20} /><Text style={styles.addText}>新增重要日子</Text></Pressable>
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filters}>{([['upcoming','即將到來'], ...RECURRENCE, ['inactive','已停用']] as const).map(([value, label]) => <Pressable key={value} onPress={() => setFilter(value as Filter)} style={[styles.filter, filter === value && styles.filterSelected]}><Text style={[styles.filterText, filter === value && styles.filterTextSelected]}>{label}</Text></Pressable>)}</ScrollView>
    {loading ? <ActivityIndicator color={colors.primary} /> : null}
    {message ? <Text style={styles.message}>{message}</Text> : null}
    {!loading && !visible.length ? <Text style={styles.empty}>目前沒有符合條件的重要日子</Text> : null}
    {visible.map((item) => <View key={item.id} style={[styles.card, !item.is_active && styles.inactive]}>
      <View style={styles.cardHeading}><View style={styles.flex}><Text style={styles.cardTitle}>{item.title}</Text><Text style={styles.meta}>{dateLabel(item)}｜{RECURRENCE.find(([value]) => value === item.recurrence_type)?.[1]}</Text></View><Text style={styles.audience}>{AUDIENCE.find(([value]) => value === item.audience_mode)?.[1]}</Text></View>
      <Text style={styles.detail}>{item.is_all_day ? "全天" : item.event_time}｜{REMINDERS.find(([days]) => days === item.reminder_days_before)?.[1] ?? `提前 ${item.reminder_days_before} 天`}</Text>
      {item.notes ? <Text style={styles.notes}>{item.notes}</Text> : null}
      <Text style={styles.calendarState}>{item.show_on_todo_calendar ? "會顯示於待辦行事曆" : "不顯示於待辦行事曆"}</Text>
      {item.can_edit ? <View style={styles.actions}><Pressable onPress={() => setEditing(item)} style={styles.edit}><Text style={styles.editText}>編輯</Text></Pressable><Pressable onPress={() => Alert.alert("確認刪除？", "確認後有 5 秒可以復原；逾時後也會從所有通知對象的行事曆移除。", [{ text: "取消" }, { text: "刪除", style: "destructive", onPress: () => scheduleDelete(item) }])} style={styles.delete}><Text style={styles.deleteText}>刪除</Text></Pressable></View> : <Text style={styles.readOnly}>由其他家人建立，僅能查看與接收通知。</Text>}
    </View>)}
    {editing !== undefined ? <ImportantDayModal currentUserId={user?.database_id ?? 0} initial={editing} onClose={() => setEditing(undefined)} onSaved={async () => { setEditing(undefined); setOperationMessage(editing ? "重要日子已更新" : "重要日子已儲存"); await load(); }} request={authorizedRequest} users={users} /> : null}
    {pendingDeletion ? <View accessibilityLiveRegion="polite" style={styles.undoBar}><Text style={styles.undoMessage}>已排定刪除「{pendingDeletion.title}」</Text><Pressable onPress={undoDelete}><Text style={styles.undoAction}>復原</Text></Pressable></View> : null}
    {operationMessage && !pendingDeletion ? <View accessibilityLiveRegion="polite" style={styles.undoBar}><Text style={styles.undoMessage}>{operationMessage}</Text></View> : null}
  </AppShell>;
}

function dateLabel(item: ImportantDay): string {
  if (item.recurrence_type === "fixed_annual") return `每年 ${item.event_month}/${item.event_day} ～ ${item.event_end_month ?? item.event_month}/${item.event_end_day ?? item.event_day}`;
  if (item.recurrence_type === "flexible_annual") return item.current_year_date ? `${item.current_year_date} ～ ${item.current_year_end_date ?? item.current_year_date}` : `${item.current_year} 年日期尚未設定`;
  return item.event_date ? `${item.event_date} ～ ${item.event_end_date ?? item.event_date}` : "尚未設定";
}

function ImportantDayModal({ currentUserId, initial, onClose, onSaved, request, users }: { currentUserId: number; initial: ImportantDay | null; onClose: () => void; onSaved: () => Promise<void>; request: ReturnType<typeof useAuth>["authorizedRequest"]; users: ImportantDayUser[] }) {
  const { colors, theme } = useAppPreferences(); const styles = createStyles(colors, theme);
  const [title, setTitle] = useState(initial?.title ?? "");
  const [recurrence, setRecurrence] = useState<ImportantDay["recurrence_type"]>(initial?.recurrence_type ?? "one_time");
  const initialDate = initial?.recurrence_type === "fixed_annual" ? `${new Date().getFullYear()}-${String(initial.event_month).padStart(2, "0")}-${String(initial.event_day).padStart(2, "0")}` : initial?.event_date ?? initial?.current_year_date ?? todayIsoDate();
  const initialEndDate = initial?.recurrence_type === "fixed_annual" ? `${new Date().getFullYear()}-${String(initial.event_end_month ?? initial.event_month).padStart(2, "0")}-${String(initial.event_end_day ?? initial.event_day).padStart(2, "0")}` : initial?.event_end_date ?? initial?.current_year_end_date ?? initialDate;
  const [selectedDate, setSelectedDate] = useState(initialDate);
  const [selectedEndDate, setSelectedEndDate] = useState(initialEndDate);
  const [dateSelectionStarted, setDateSelectionStarted] = useState(false);
  const [allDay, setAllDay] = useState(initial?.is_all_day ?? true);
  const [eventTime, setEventTime] = useState(initial?.event_time ?? "09:00");
  const [reminder, setReminder] = useState(initial?.reminder_days_before ?? 0);
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [audience, setAudience] = useState<ImportantDay["audience_mode"]>(initial?.audience_mode ?? "self");
  const [recipients, setRecipients] = useState<number[]>(initial?.recipient_ids ?? [currentUserId]);
  const [showCalendar, setShowCalendar] = useState(initial?.show_on_todo_calendar ?? true);
  const [active, setActive] = useState(initial?.is_active ?? true);
  const [saving, setSaving] = useState(false); const [error, setError] = useState<string | null>(null);
  const mutationInFlight = useRef(false);
  const [calendarMonth, setCalendarMonth] = useState(initialDate.slice(0, 7));
  const [calendarData, setCalendarData] = useState<Pick<TodoAnalytics, "calendar_counts" | "calendar_days">>({ calendar_counts: {}, calendar_days: {} });
  useEffect(() => {
    const dateInMonth = selectedDate.slice(0, 7) === calendarMonth ? selectedDate : `${calendarMonth}-01`;
    void getAnalytics(request, "todos", { start: dateInMonth, end: dateInMonth }, { calendarMonth })
      .then((result) => setCalendarData({ calendar_counts: result.calendar_counts, calendar_days: result.calendar_days ?? {} }))
      .catch(() => setCalendarData({ calendar_counts: {}, calendar_days: {} }));
  }, [calendarMonth, request, selectedDate]);
  const payload = { title, recurrence_type: recurrence, event_date: recurrence === "flexible_annual" ? null : selectedDate, event_end_date: recurrence === "flexible_annual" ? null : selectedEndDate, occurrence_date: recurrence === "flexible_annual" ? selectedDate : null, occurrence_end_date: recurrence === "flexible_annual" ? selectedEndDate : null, event_time: allDay ? null : eventTime, is_all_day: allDay, reminder_days_before: reminder, notes, audience_mode: audience, recipient_ids: recipients, show_on_todo_calendar: showCalendar, is_active: active };
  const save = async () => {
    if (mutationInFlight.current) return;
    mutationInFlight.current = true;
    setSaving(true); setError(null);
    try {
      if (initial) await updateImportantDay(request, initial.id, payload);
      else await createImportantDay(request, payload);
      await onSaved();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "儲存失敗，內容已保留，請確認網路後重試");
    } finally {
      mutationInFlight.current = false;
      setSaving(false);
    }
  };
  return <Modal animationType="fade" transparent visible onRequestClose={onClose}><View style={styles.modalRoot}><Pressable onPress={onClose} style={styles.backdrop} /><View style={styles.modalCard}><Pressable onPress={onClose} style={styles.close}><MaterialCommunityIcons color={colors.textMuted} name="close" size={24} /></Pressable><ScrollView contentContainerStyle={styles.modalContent}>
    <Text style={styles.modalTitle}>{initial ? "編輯重要日子" : "新增重要日子"}</Text>
    <Field label="名稱" value={title} onChange={setTitle} placeholder="請輸入重要日子名稱" />
    <Text style={styles.label}>類型</Text><Options options={RECURRENCE} selected={recurrence} setSelected={(value) => setRecurrence(value as ImportantDay["recurrence_type"])} />
    <Text style={styles.label}>日期</Text><Text style={styles.recipientHint}>{selectedDate} ～ {selectedEndDate}（依序點選開始與結束日；只選一天即為單日）</Text><View style={styles.calendar}><Calendar current={selectedDate} dayComponent={({ date: calendarDate, state }) => { if (!calendarDate) return null; const inRange = calendarDate.dateString >= selectedDate && calendarDate.dateString <= selectedEndDate; const isStart = calendarDate.dateString === selectedDate; const isEnd = calendarDate.dateString === selectedEndDate; const isToday = calendarDate.dateString === todayIsoDate(); const calendarDay = calendarData.calendar_days[calendarDate.dateString]; const count = calendarData.calendar_counts[calendarDate.dateString] ?? 0; const selectDay = () => { if (!dateSelectionStarted) { setSelectedDate(calendarDate.dateString); setSelectedEndDate(calendarDate.dateString); setDateSelectionStarted(true); } else { if (calendarDate.dateString < selectedDate) { setSelectedEndDate(selectedDate); setSelectedDate(calendarDate.dateString); } else setSelectedEndDate(calendarDate.dateString); setDateSelectionStarted(false); } }; return <Pressable onPress={selectDay} style={[styles.calendarDay, inRange && styles.calendarRangeDay, isStart && styles.calendarRangeStart, isEnd && styles.calendarRangeEnd, isToday && styles.calendarToday]}><Text style={[styles.calendarDayNumber, state === "disabled" && styles.calendarDayDisabled, calendarDay?.is_holiday && styles.calendarHolidayText, (isStart || isEnd) && styles.calendarDaySelectedText, isToday && styles.calendarTodayText]}>{calendarDate.day}</Text>{count > 0 ? <Text style={styles.calendarCount}>{count}件</Text> : <View style={styles.calendarMetaPlaceholder} />}{calendarDay?.name ? <Text numberOfLines={1} style={[styles.calendarLabel, styles.calendarHolidayLabel]}>{calendarDay.name}</Text> : <View style={styles.calendarLabelPlaceholder} />}{uniqueImportantDayLabels(calendarDay).map((notification) => <Text key={`${calendarDate.dateString}-${notification}`} numberOfLines={1} style={styles.calendarNotification}>{notification}</Text>)}</Pressable>; }} onDayPress={(day: DateData) => { if (!dateSelectionStarted) { setSelectedDate(day.dateString); setSelectedEndDate(day.dateString); setDateSelectionStarted(true); } else { setSelectedEndDate(day.dateString >= selectedDate ? day.dateString : selectedDate); if (day.dateString < selectedDate) setSelectedDate(day.dateString); setDateSelectionStarted(false); } }} onMonthChange={(month) => setCalendarMonth(month.dateString.slice(0, 7))} theme={{ calendarBackground: colors.surface, dayTextColor: colors.text, monthTextColor: colors.text, arrowColor: colors.primary, textSectionTitleColor: colors.textMuted, textDisabledColor: theme === "dark" ? "#52645F" : "#C4CECB", todayTextColor: colors.danger }} /></View>
    <View style={styles.switchRow}><Text style={styles.label}>全天</Text><Switch value={allDay} onValueChange={setAllDay} /></View>{!allDay ? <TimePickerField value={eventTime} onChange={setEventTime} /> : null}
    <Text style={styles.label}>提前提醒</Text><Options options={REMINDERS.map(([value, label]) => [String(value), label] as const)} selected={String(reminder)} setSelected={(value) => setReminder(Number(value))} />
    <Text style={styles.label}>通知對象</Text><Options options={AUDIENCE} selected={audience} setSelected={(value) => setAudience(value as ImportantDay["audience_mode"])} />
    {audience === "specific" ? <><View style={styles.people}>{users.map((person) => { const selected = recipients.includes(person.id); return <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: selected }} key={person.id} onPress={() => setRecipients((current) => current.includes(person.id) ? current.filter((id) => id !== person.id) : [...current, person.id])} style={[styles.person, selected && styles.personSelected]}><MaterialCommunityIcons color={selected ? (theme === "dark" ? colors.background : colors.white) : colors.primary} name={selected ? "checkbox-marked" : "checkbox-blank-outline"} size={20} /><Text style={[styles.personText, selected && styles.personTextSelected]}>{person.role} ({person.user_id})</Text></Pressable>; })}</View><Text style={styles.recipientHint}>{users.length > 1 ? `已選擇 ${recipients.length} 位家人` : "目前只有 1 位使用者可供選擇"}</Text></> : null}
    <Field label="備註" value={notes} onChange={setNotes} placeholder="可填寫地點或其他說明" multiline />
    <View style={styles.switchRow}><Text style={styles.label}>顯示於待辦行事曆</Text><Switch value={showCalendar} onValueChange={setShowCalendar} /></View>
    <View style={styles.switchRow}><Text style={styles.label}>啟用事件</Text><Switch value={active} onValueChange={setActive} /></View>
    {error ? <Text style={styles.message}>{error}</Text> : null}<View style={styles.actions}><Pressable onPress={onClose} style={styles.cancel}><Text style={styles.cancelText}>取消</Text></Pressable><Pressable disabled={saving} onPress={() => void save()} style={styles.save}><Text style={styles.saveText}>{saving ? "儲存中…" : "確認"}</Text></Pressable></View>
  </ScrollView></View></View></Modal>;
}

function Field({ label, multiline, onChange, placeholder, value }: { label: string; multiline?: boolean; onChange: (value: string) => void; placeholder: string; value: string }) { const { colors, theme } = useAppPreferences(); const styles = createStyles(colors, theme); return <View style={styles.field}><Text style={styles.label}>{label}</Text><TextInput multiline={multiline} onChangeText={onChange} placeholder={placeholder} placeholderTextColor={colors.textMuted} style={[styles.input, styles.iosInputFontSize, multiline && styles.multiline]} value={value} /></View>; }
function Options({ options, selected, setSelected }: { options: readonly (readonly [string, string])[]; selected: string; setSelected: (value: string) => void }) { const { colors, theme } = useAppPreferences(); const styles = createStyles(colors, theme); return <View style={styles.options}>{options.map(([value, label]) => <Pressable key={value} onPress={() => setSelected(value)} style={[styles.option, selected === value && styles.optionSelected]}><Text style={[styles.optionText, selected === value && styles.optionTextSelected]}>{label}</Text></Pressable>)}</View>; }

const createStyles = (colors: ReturnType<typeof useAppPreferences>["colors"], theme: ReturnType<typeof useAppPreferences>["theme"]) => StyleSheet.create({
  flex: { flex: 1 }, intro: { alignItems: "flex-start", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 18, borderWidth: 1, flexDirection: "row", gap: 12, padding: 18 }, introTitle: { color: colors.text, fontSize: 20, fontWeight: "900" }, description: { color: colors.textMuted, fontSize: 12, lineHeight: 18, marginTop: 5 }, addButton: { alignItems: "center", alignSelf: "flex-start", backgroundColor: colors.primary, borderRadius: 11, flexDirection: "row", gap: 7, paddingHorizontal: 16, paddingVertical: 11 }, addText: { color: theme === "dark" ? colors.background : colors.white, fontWeight: "900" }, filters: { gap: 8 }, filter: { backgroundColor: colors.primarySoft, borderRadius: 18, paddingHorizontal: 14, paddingVertical: 8 }, filterSelected: { backgroundColor: colors.primary }, filterText: { color: colors.primaryDark, fontWeight: "800" }, filterTextSelected: { color: theme === "dark" ? colors.background : colors.white }, message: { color: colors.danger, fontWeight: "700", textAlign: "center" }, empty: { color: colors.textMuted, padding: 24, textAlign: "center" }, card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 16, borderWidth: 1, gap: 8, padding: 17 }, inactive: { opacity: .6 }, cardHeading: { alignItems: "flex-start", flexDirection: "row", gap: 10 }, cardTitle: { color: colors.text, fontSize: 17, fontWeight: "900" }, meta: { color: colors.textMuted, fontSize: 11, marginTop: 4 }, audience: { backgroundColor: colors.primarySoft, borderRadius: 14, color: colors.primaryDark, fontSize: 11, fontWeight: "800", paddingHorizontal: 9, paddingVertical: 4 }, detail: { color: colors.text, fontSize: 13 }, notes: { color: colors.textMuted, fontSize: 12, lineHeight: 18 }, calendarState: { color: colors.primaryDark, fontSize: 11, fontWeight: "700" }, actions: { flexDirection: "row", gap: 8, justifyContent: "flex-end" }, edit: { backgroundColor: colors.primarySoft, borderRadius: 9, paddingHorizontal: 14, paddingVertical: 8 }, editText: { color: colors.primaryDark, fontWeight: "800" }, delete: { backgroundColor: theme === "dark" ? "#432823" : "#FAD7D5", borderRadius: 9, paddingHorizontal: 14, paddingVertical: 8 }, deleteText: { color: colors.danger, fontWeight: "800" }, readOnly: { color: colors.textMuted, fontSize: 11 }, modalRoot: { alignItems: "center", flex: 1, justifyContent: "center", padding: 18 }, backdrop: { backgroundColor: "rgba(18,35,32,.5)", bottom: 0, left: 0, position: "absolute", right: 0, top: 0 }, modalCard: { backgroundColor: colors.surface, borderRadius: 20, maxHeight: "94%", maxWidth: 600, width: "100%" }, close: { padding: 12, position: "absolute", right: 4, top: 4, zIndex: 2 }, modalContent: { gap: 13, padding: 22, paddingTop: 45 }, modalTitle: { color: colors.text, fontSize: 22, fontWeight: "900" }, field: { gap: 7 }, label: { color: colors.text, fontSize: 14, fontWeight: "800" }, input: { backgroundColor: theme === "dark" ? "#22332F" : colors.white, borderColor: colors.border, borderRadius: 11, borderWidth: 1, color: colors.text, padding: 12 }, multiline: { minHeight: 90, textAlignVertical: "top" }, options: { flexDirection: "row", flexWrap: "wrap", gap: 8 }, option: { backgroundColor: colors.primarySoft, borderColor: colors.border, borderRadius: 16, borderWidth: 1, paddingHorizontal: 13, paddingVertical: 8 }, optionSelected: { backgroundColor: colors.primary }, optionText: { color: colors.primaryDark, fontWeight: "800" }, optionTextSelected: { color: theme === "dark" ? colors.background : colors.white }, calendar: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 14, borderWidth: 1, overflow: "hidden" }, switchRow: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" }, people: { flexDirection: "row", flexWrap: "wrap", gap: 8 }, person: { alignItems: "center", backgroundColor: colors.primarySoft, borderColor: colors.border, borderRadius: 10, borderWidth: 1, flexDirection: "row", gap: 5, padding: 9 }, personSelected: { backgroundColor: colors.primary, borderColor: colors.primary }, personText: { color: colors.primaryDark, fontWeight: "800" }, personTextSelected: { color: theme === "dark" ? colors.background : colors.white }, recipientHint: { color: colors.textMuted, fontSize: 11 }, cancel: { borderColor: colors.border, borderRadius: 10, borderWidth: 1, paddingHorizontal: 18, paddingVertical: 10 }, cancelText: { color: colors.textMuted, fontWeight: "800" }, save: { backgroundColor: colors.primary, borderRadius: 10, paddingHorizontal: 20, paddingVertical: 10 }, saveText: { color: theme === "dark" ? colors.background : colors.white, fontWeight: "900" }, saveTextLight: { color: colors.white },
  calendarDay: { alignItems: "center", height: 76, justifyContent: "center", overflow: "hidden", paddingHorizontal: 1, width: "100%" },
  iosInputFontSize: { fontSize: 16 },
  calendarDaySelected: { backgroundColor: colors.primary, borderRadius: 10 },
  calendarRangeDay: { backgroundColor: theme === "dark" ? "#214B43" : "#D7EFEB" },
  calendarRangeStart: { backgroundColor: colors.primary, borderBottomLeftRadius: 18, borderTopLeftRadius: 18 },
  calendarRangeEnd: { backgroundColor: colors.primary, borderBottomRightRadius: 18, borderTopRightRadius: 18 },
  calendarToday: { backgroundColor: colors.danger, borderRadius: 10 },
  calendarDayNumber: { color: colors.text, fontSize: 15 },
  calendarDayDisabled: { color: theme === "dark" ? "#52645F" : "#C4CECB" },
  calendarDaySelectedText: { color: theme === "dark" ? colors.background : colors.white, fontWeight: "800" },
  calendarTodayText: { color: colors.white, fontWeight: "900" },
  calendarHolidayText: { color: colors.danger, fontWeight: "800" },
  calendarCount: { color: theme === "dark" ? colors.accent : "#111111", fontSize: 11, fontWeight: "900", lineHeight: 14 },
  calendarMetaPlaceholder: { height: 14 },
  calendarLabel: { color: colors.textMuted, fontSize: 10, fontWeight: "700", lineHeight: 13, maxWidth: "100%" },
  calendarHolidayLabel: { color: colors.danger },
  calendarLabelPlaceholder: { height: 13 },
  calendarNotification: { color: IMPORTANT_DAY_COLOR, fontSize: 10, fontWeight: "800", lineHeight: 13, maxWidth: "100%" },
  undoBar: { alignItems: "center", alignSelf: "center", backgroundColor: colors.primaryDark, borderRadius: 20, bottom: 22, flexDirection: "row", gap: 14, paddingHorizontal: 18, paddingVertical: 10, position: "absolute", zIndex: 20 },
  undoMessage: { color: colors.white, fontWeight: "800" },
  undoAction: { color: "#FFD18A", fontWeight: "900", textDecorationLine: "underline" },
});
