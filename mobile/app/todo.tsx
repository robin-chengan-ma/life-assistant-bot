import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";
import { Redirect, useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, Modal, ScrollView, StyleSheet, TextInput } from "react-native";

import { AppPressable as Pressable } from "@/components/AppPressable";
import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";
import { AppShell } from "@/components/AppShell";
import { todayIsoDate } from "@/components/DateRangeFilter";
import { TodoCalendarPicker } from "@/components/TodoCalendarPicker";
import { useAppPreferences } from "@/context/AppPreferencesContext";
import { useAuth } from "@/context/AuthContext";
import {
  createTodo,
  deleteTodo,
  getTodos,
  updateTodo,
  type TodoItem,
  type TodoRecurrenceType,
} from "@/services/analyticsApi";

function formatDateRange(start: string, end: string): string {
  return start === end ? start : `${start} ～ ${end}`;
}

// 待辦類型：一次性（既有的日期區間邏輯）／常態性（每月固定一天重複提醒，2026-11-28 新增，
// 見 docs/ADR/discuss/robinson.md——Robin 不想每個月手動新增信用卡/車貸繳費這種固定提醒）。
const RECURRENCE_TYPE_OPTIONS: Array<{ label: string; value: TodoRecurrenceType }> = [
  { label: "一次性", value: "once" },
  { label: "常態性（每月固定一天）", value: "monthly" },
];

function formatTodoDate(item: Pick<TodoItem, "recurrence_type" | "recurrence_day" | "remind_start_date" | "remind_end_date">): string {
  if (item.recurrence_type === "monthly") return `每月 ${item.recurrence_day} 號`;
  return formatDateRange(item.remind_start_date ?? "", item.remind_end_date ?? "");
}

// 提前提醒天數可選項，跟生日設定完全一樣，新增時預設只勾「當天」（0）。
const REMIND_OFFSET_OPTIONS: Array<{ label: string; value: number }> = [
  { label: "14 天前", value: 14 },
  { label: "7 天前", value: 7 },
  { label: "3 天前", value: 3 },
  { label: "當天", value: 0 },
];

function formatRemindOffsets(offsets: number[] | undefined): string {
  const values = offsets && offsets.length ? offsets : [0];
  const sorted = values.slice().sort((left, right) => right - left);
  return `提前提醒：${sorted.map((value) => (value === 0 ? "當天" : `${value} 天前`)).join("、")}`;
}

// 待辦事項：純粹的一次性提醒，只有日期與文字內容；沒有完成／逾期狀態，使用者不需要額外確認動作。
export default function TodoScreen() {
  const { authorizedRequest, status } = useAuth();
  const { colors, theme } = useAppPreferences();
  const styles = createStyles(colors, theme);
  const { action } = useLocalSearchParams<{ action?: string }>();
  const [items, setItems] = useState<TodoItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [operationMessage, setOperationMessage] = useState<string | null>(null);
  const [editing, setEditing] = useState<TodoItem | null | undefined>(undefined);
  const [pendingDeletion, setPendingDeletion] = useState<TodoItem | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<TodoItem | null>(null);
  // 已過期／進行中頁籤：以 remind_end_date（區間最後一天）跟今天比較，還沒整段結束都算進行中。
  const [tab, setTab] = useState<"active" | "expired">("active");
  const deleteTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const autoOpenHandled = useRef(false);

  // 2026-11-27（見 docs/ADR/discuss/robinson.md）：Robin 要求首頁「新增待辦」按鈕要直接跳出新增
  // 表單彈窗，不要先進列表頁再按一次「新增待辦」。首頁改用 `/todo?action=new` 導頁，這裡偵測到
  // 該參數時自動開啟新增表單（只在進頁當下觸發一次，避免返回頁面時殘留參數又重複彈出）。
  useEffect(() => {
    if (action === "new" && !autoOpenHandled.current) {
      autoOpenHandled.current = true;
      setEditing(null);
    }
  }, [action]);

  const load = useCallback(async () => {
    if (status !== "authenticated") return;
    setLoading(true); setMessage(null);
    try { const result = await getTodos(authorizedRequest); setItems(result.items); }
    catch (error) { setMessage(error instanceof Error ? error.message : "目前無法連接資料服務，請稍後再試"); }
    finally { setLoading(false); }
  }, [authorizedRequest, status]);
  useEffect(() => { void load(); }, [load]);

  const scheduleDelete = (item: TodoItem) => {
    setDeleteTarget(null);
    if (pendingDeletion) return;
    setPendingDeletion(item); setOperationMessage("已排定刪除，5 秒內可復原");
    deleteTimer.current = setTimeout(() => {
      void deleteTodo(authorizedRequest, item.id)
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

  // 常態性（monthly）待辦沒有「結束日期」，每個月都會重複，永遠排在「進行中」，不會被歸類成已過期。
  const sorted = items.slice().sort((left, right) => {
    if (left.recurrence_type === "monthly" && right.recurrence_type !== "monthly") return 1;
    if (right.recurrence_type === "monthly" && left.recurrence_type !== "monthly") return -1;
    if (left.recurrence_type === "monthly" && right.recurrence_type === "monthly") {
      return (left.recurrence_day ?? 0) - (right.recurrence_day ?? 0);
    }
    return (left.remind_start_date ?? "").localeCompare(right.remind_start_date ?? "");
  });

  const todayIso = todayIsoDate();
  const expired = sorted.filter((item) => item.recurrence_type !== "monthly" && (item.remind_end_date ?? "") < todayIso);
  const active = sorted.filter((item) => item.recurrence_type === "monthly" || (item.remind_end_date ?? "") >= todayIso);
  const visible = tab === "active" ? active : expired;

  if (status === "guest") return <Redirect href="/login" />;
  if (loading && !items.length && !message) return <AppShell title="待辦事項"><View style={{ alignItems: "center", gap: 12, justifyContent: "center", minHeight: 360 }}><ActivityIndicator color={colors.primary} size="large" /><Text style={{ color: colors.textMuted, fontWeight: "700" }}>資料載入中…</Text></View></AppShell>;
  return <AppShell title="待辦事項">
    <View style={styles.intro}><MaterialCommunityIcons color={colors.primary} name="calendar-check-outline" size={28} /><View style={styles.flex}><Text style={styles.introTitle}>待辦提醒</Text><Text style={styles.description}>到了日期會推播提醒，不需要標記完成。新增待辦請到首頁點「新增待辦」。</Text></View></View>
    <View style={styles.tabRow}>
      <Pressable onPress={() => setTab("active")} style={[styles.tab, tab === "active" ? styles.tabSelected : null]}><Text style={[styles.tabText, tab === "active" ? styles.tabTextSelected : null]}>進行中（{active.length}）</Text></Pressable>
      <Pressable onPress={() => setTab("expired")} style={[styles.tab, tab === "expired" ? styles.tabSelected : null]}><Text style={[styles.tabText, tab === "expired" ? styles.tabTextSelected : null]}>已過期（{expired.length}）</Text></Pressable>
    </View>
    {loading ? <ActivityIndicator color={colors.primary} /> : null}
    {message ? <Text style={styles.message}>{message}</Text> : null}
    {!loading && !visible.length ? <Text style={styles.empty}>{tab === "active" ? "目前沒有進行中的待辦事項" : "目前沒有已過期的待辦事項"}</Text> : null}
    {visible.map((item) => <View key={item.id} style={styles.card}>
      <View style={styles.cardHeading}><Text style={styles.cardTitle}>{item.content}</Text><Text style={styles.meta}>{formatTodoDate(item)}</Text></View>
      <Text style={styles.remindMeta}>{formatRemindOffsets(item.remind_offsets)}</Text>
      {item.can_edit ? <View style={styles.actions}><Pressable onPress={() => setEditing(item)} style={styles.edit}><Text style={styles.editText}>編輯</Text></Pressable><Pressable onPress={() => setDeleteTarget(item)} style={styles.delete}><Text style={styles.deleteText}>刪除</Text></Pressable></View> : <Text style={styles.readOnly}>由其他家人建立，僅能查看。</Text>}
    </View>)}
    {editing !== undefined ? <TodoModal initial={editing} onClose={() => setEditing(undefined)} onSaved={async () => { setEditing(undefined); setOperationMessage(editing ? "待辦已更新" : "待辦已儲存"); await load(); }} request={authorizedRequest} /> : null}
    <Modal animationType="fade" onRequestClose={() => setDeleteTarget(null)} transparent visible={Boolean(deleteTarget)}><View style={styles.deleteBackdrop}><View style={styles.deleteCard}><Text style={styles.deleteTitle}>確認刪除？</Text><Text style={styles.deleteBody}>確認後有 5 秒可以復原。</Text><View style={styles.actions}><Pressable onPress={() => setDeleteTarget(null)} style={styles.edit}><Text style={styles.editText}>取消</Text></Pressable><Pressable onPress={() => deleteTarget && scheduleDelete(deleteTarget)} style={styles.delete}><Text style={styles.deleteText}>刪除</Text></Pressable></View></View></View></Modal>
    {pendingDeletion ? <View accessibilityLiveRegion="polite" style={styles.undoBar}><Text style={styles.undoMessage}>已排定刪除「{pendingDeletion.content}」</Text><Pressable onPress={undoDelete}><Text style={styles.undoAction}>復原</Text></Pressable></View> : null}
    {operationMessage && !pendingDeletion ? <View accessibilityLiveRegion="polite" style={styles.undoBar}><Text style={styles.undoMessage}>{operationMessage}</Text></View> : null}
  </AppShell>;
}

function TodoModal({ initial, onClose, onSaved, request }: { initial: TodoItem | null; onClose: () => void; onSaved: () => Promise<void>; request: ReturnType<typeof useAuth>["authorizedRequest"] }) {
  const { colors, theme } = useAppPreferences(); const styles = createStyles(colors, theme);
  const [content, setContent] = useState(initial?.content ?? "");
  const [recurrenceType, setRecurrenceType] = useState<TodoRecurrenceType>(initial?.recurrence_type ?? "once");
  const [recurrenceDay, setRecurrenceDay] = useState(initial?.recurrence_day ? String(initial.recurrence_day) : "");
  const [remindStartDate, setRemindStartDate] = useState(initial?.remind_start_date ?? todayIsoDate());
  const [remindEndDate, setRemindEndDate] = useState(initial?.remind_end_date ?? initial?.remind_start_date ?? todayIsoDate());
  const [remindOffsets, setRemindOffsets] = useState<number[]>(initial?.remind_offsets?.length ? initial.remind_offsets : [0]);
  const [saving, setSaving] = useState(false); const [error, setError] = useState<string | null>(null);
  const mutationInFlight = useRef(false);

  const toggleOffset = (value: number) => {
    setRemindOffsets((current) => {
      if (current.includes(value)) {
        const next = current.filter((item) => item !== value);
        return next.length ? next : current;
      }
      return [...current, value];
    });
  };

  const validate = (): string | null => {
    if (!content.trim()) return "請輸入待辦內容";
    if (recurrenceType === "monthly") {
      const dayValue = Number(recurrenceDay);
      if (!Number.isInteger(dayValue) || dayValue < 1 || dayValue > 31) return "請輸入 1 到 31 之間的每月固定日期";
    } else {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(remindStartDate) || !/^\d{4}-\d{2}-\d{2}$/.test(remindEndDate)) return "請選擇提醒日期";
      if (remindEndDate < remindStartDate) return "提醒結束日期不可早於開始日期";
    }
    if (!remindOffsets.length) return "請至少選擇一個提前提醒天數";
    return null;
  };

  const save = async () => {
    const validationError = validate();
    if (validationError) { setError(validationError); return; }
    if (mutationInFlight.current) return;
    mutationInFlight.current = true;
    setSaving(true); setError(null);
    const payload = recurrenceType === "monthly"
      ? { content: content.trim(), remind_offsets: remindOffsets, recurrence_type: "monthly" as const, recurrence_day: Number(recurrenceDay) }
      : { content: content.trim(), remind_offsets: remindOffsets, recurrence_type: "once" as const, remind_start_date: remindStartDate, remind_end_date: remindEndDate };
    try {
      if (initial) await updateTodo(request, initial.id, payload);
      else await createTodo(request, payload);
      await onSaved();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "儲存失敗，請確認網路後重試");
    } finally {
      mutationInFlight.current = false;
      setSaving(false);
    }
  };

  return <Modal animationType="fade" transparent visible onRequestClose={onClose}><View style={styles.modalRoot}><Pressable onPress={onClose} style={styles.backdrop} /><View style={styles.modalCard}><Pressable onPress={onClose} style={styles.close}><MaterialCommunityIcons color={colors.textMuted} name="close" size={24} /></Pressable><ScrollView contentContainerStyle={styles.modalContent}>
    <Text style={styles.modalTitle}>{initial ? "編輯待辦" : "新增待辦"}</Text>
    <View style={styles.field}>
      <Text style={styles.label}>待辦類型</Text>
      <View style={styles.chipRow}>
        {RECURRENCE_TYPE_OPTIONS.map((option) => {
          const selected = recurrenceType === option.value;
          return <Pressable key={option.value} onPress={() => setRecurrenceType(option.value)} style={[styles.chip, selected ? styles.chipSelected : null]}>
            <Text style={[styles.chipText, selected ? styles.chipTextSelected : null]}>{option.label}</Text>
          </Pressable>;
        })}
      </View>
    </View>
    {recurrenceType === "monthly"
      ? <View style={styles.field}><Text style={styles.label}>每月固定日期</Text><TextInput inputMode="numeric" onChangeText={(value) => setRecurrenceDay(value.replace(/\D/g, ""))} placeholder="1-31" placeholderTextColor={colors.textMuted} style={[styles.input, styles.iosInputFontSize]} value={recurrenceDay} /></View>
      : <TodoCalendarPicker endDate={remindEndDate} onChange={(range) => { setRemindStartDate(range.start); setRemindEndDate(range.end); }} startDate={remindStartDate} />}
    <View style={styles.field}><Text style={styles.label}>內容</Text><TextInput multiline onChangeText={setContent} placeholder="請輸入待辦內容" placeholderTextColor={colors.textMuted} style={[styles.input, styles.multiline, styles.iosInputFontSize]} value={content} /></View>
    <View style={styles.field}>
      <Text style={styles.label}>提前提醒（可複選）</Text>
      <View style={styles.chipRow}>
        {REMIND_OFFSET_OPTIONS.map((option) => {
          const selected = remindOffsets.includes(option.value);
          return <Pressable key={option.value} onPress={() => toggleOffset(option.value)} style={[styles.chip, selected ? styles.chipSelected : null]}>
            <Text style={[styles.chipText, selected ? styles.chipTextSelected : null]}>{option.label}</Text>
          </Pressable>;
        })}
      </View>
    </View>
    {error ? <Text style={styles.message}>{error}</Text> : null}
    <View style={styles.actions}><Pressable onPress={onClose} style={styles.cancel}><Text style={styles.cancelText}>取消</Text></Pressable><Pressable disabled={saving} onPress={() => void save()} style={styles.save}><Text style={styles.saveText}>{saving ? "儲存中…" : "確認"}</Text></Pressable></View>
  </ScrollView></View></View></Modal>;
}

const createStyles = (colors: ReturnType<typeof useAppPreferences>["colors"], theme: ReturnType<typeof useAppPreferences>["theme"]) => StyleSheet.create({
  flex: { flex: 1 }, intro: { alignItems: "flex-start", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 18, borderWidth: 1, flexDirection: "row", gap: 12, padding: 18 }, introTitle: { color: colors.text, fontSize: 20, fontWeight: "900" }, description: { color: colors.textMuted, fontSize: 12, lineHeight: 18, marginTop: 5 },
  tabRow: { flexDirection: "row", gap: 8 }, tab: { backgroundColor: theme === "dark" ? "#22332F" : colors.white, borderColor: colors.border, borderRadius: 11, borderWidth: 1, flex: 1, paddingVertical: 11 }, tabSelected: { backgroundColor: colors.primary, borderColor: colors.primary }, tabText: { color: colors.text, fontWeight: "800", textAlign: "center" }, tabTextSelected: { color: theme === "dark" ? colors.background : colors.white },
  message: { color: colors.danger, fontWeight: "700", textAlign: "center" }, empty: { color: colors.textMuted, padding: 24, textAlign: "center" }, card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 16, borderWidth: 1, gap: 8, padding: 17 }, cardHeading: { alignItems: "flex-start", flexDirection: "row", gap: 10, justifyContent: "space-between" }, cardTitle: { color: colors.text, flex: 1, fontSize: 16, fontWeight: "900" }, meta: { color: colors.textMuted, fontSize: 12, fontWeight: "700" },
  actions: { flexDirection: "row", gap: 8, justifyContent: "flex-end" }, edit: { backgroundColor: colors.primarySoft, borderRadius: 9, paddingHorizontal: 14, paddingVertical: 8 }, editText: { color: colors.primaryDark, fontWeight: "800" }, delete: { backgroundColor: theme === "dark" ? "#432823" : "#FAD7D5", borderRadius: 9, paddingHorizontal: 14, paddingVertical: 8 }, deleteText: { color: colors.danger, fontWeight: "800" }, readOnly: { color: colors.textMuted, fontSize: 11 }, remindMeta: { color: colors.textMuted, fontSize: 12, fontWeight: "700" },
  modalRoot: { alignItems: "center", flex: 1, justifyContent: "center", padding: 18 }, backdrop: { backgroundColor: "rgba(18,35,32,.5)", bottom: 0, left: 0, position: "absolute", right: 0, top: 0 }, modalCard: { backgroundColor: colors.surface, borderRadius: 20, maxHeight: "94%", maxWidth: 480, width: "100%" }, close: { padding: 12, position: "absolute", right: 4, top: 4, zIndex: 2 }, modalContent: { gap: 13, padding: 22, paddingTop: 45 }, modalTitle: { color: colors.text, fontSize: 22, fontWeight: "900" },
  field: { gap: 7 }, label: { color: colors.text, fontSize: 14, fontWeight: "800" }, input: { backgroundColor: theme === "dark" ? "#22332F" : colors.white, borderColor: colors.border, borderRadius: 11, borderWidth: 1, color: colors.text, padding: 12 }, multiline: { minHeight: 90, textAlignVertical: "top" }, iosInputFontSize: { fontSize: 16 },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 }, chip: { backgroundColor: theme === "dark" ? "#22332F" : colors.white, borderColor: colors.border, borderRadius: 999, borderWidth: 1, paddingHorizontal: 14, paddingVertical: 8 }, chipSelected: { backgroundColor: colors.primary, borderColor: colors.primary }, chipText: { color: colors.text, fontWeight: "700" }, chipTextSelected: { color: theme === "dark" ? colors.background : colors.white },
  cancel: { borderColor: colors.border, borderRadius: 10, borderWidth: 1, paddingHorizontal: 18, paddingVertical: 10 }, cancelText: { color: colors.textMuted, fontWeight: "800" }, save: { backgroundColor: colors.primary, borderRadius: 10, paddingHorizontal: 20, paddingVertical: 10 }, saveText: { color: theme === "dark" ? colors.background : colors.white, fontWeight: "900" },
  deleteBackdrop: { alignItems: "center", backgroundColor: "rgba(18,35,32,.5)", flex: 1, justifyContent: "center", padding: 20 }, deleteCard: { backgroundColor: colors.surface, borderRadius: 20, gap: 14, maxWidth: 420, padding: 24, width: "100%" }, deleteTitle: { color: colors.text, fontSize: 20, fontWeight: "900" }, deleteBody: { color: colors.text, fontSize: 13, lineHeight: 20 },
  undoBar: { alignItems: "center", alignSelf: "center", backgroundColor: colors.primaryDark, borderRadius: 20, bottom: 22, flexDirection: "row", gap: 14, paddingHorizontal: 18, paddingVertical: 10, position: "absolute", zIndex: 20 },
  undoMessage: { color: colors.white, fontWeight: "800" },
  undoAction: { color: "#FFD18A", fontWeight: "900", textDecorationLine: "underline" },
});
