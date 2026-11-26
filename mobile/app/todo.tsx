import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";
import { Redirect } from "expo-router";
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
} from "@/services/analyticsApi";

function formatDateRange(start: string, end: string): string {
  return start === end ? start : `${start} ～ ${end}`;
}

// 待辦事項：純粹的一次性提醒，只有日期與文字內容；沒有完成／逾期狀態，使用者不需要額外確認動作。
export default function TodoScreen() {
  const { authorizedRequest, status } = useAuth();
  const { colors, theme } = useAppPreferences();
  const styles = createStyles(colors, theme);
  const [items, setItems] = useState<TodoItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [operationMessage, setOperationMessage] = useState<string | null>(null);
  const [editing, setEditing] = useState<TodoItem | null | undefined>(undefined);
  const [pendingDeletion, setPendingDeletion] = useState<TodoItem | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<TodoItem | null>(null);
  const deleteTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  const sorted = items.slice().sort((left, right) => left.remind_start_date.localeCompare(right.remind_start_date));

  if (status === "guest") return <Redirect href="/login" />;
  if (loading && !items.length && !message) return <AppShell title="待辦事項"><View style={{ alignItems: "center", gap: 12, justifyContent: "center", minHeight: 360 }}><ActivityIndicator color={colors.primary} size="large" /><Text style={{ color: colors.textMuted, fontWeight: "700" }}>資料載入中…</Text></View></AppShell>;
  return <AppShell title="待辦事項">
    <View style={styles.intro}><MaterialCommunityIcons color={colors.primary} name="calendar-check-outline" size={28} /><View style={styles.flex}><Text style={styles.introTitle}>待辦提醒</Text><Text style={styles.description}>到了日期會推播提醒，不需要標記完成。</Text></View></View>
    <Pressable onPress={() => setEditing(null)} style={styles.addButton}><MaterialCommunityIcons color={theme === "dark" ? colors.background : colors.white} name="plus" size={20} /><Text style={styles.addText}>新增待辦</Text></Pressable>
    {loading ? <ActivityIndicator color={colors.primary} /> : null}
    {message ? <Text style={styles.message}>{message}</Text> : null}
    {!loading && !sorted.length ? <Text style={styles.empty}>目前沒有待辦事項</Text> : null}
    {sorted.map((item) => <View key={item.id} style={styles.card}>
      <View style={styles.cardHeading}><Text style={styles.cardTitle}>{item.content}</Text><Text style={styles.meta}>{formatDateRange(item.remind_start_date, item.remind_end_date)}</Text></View>
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
  const [remindStartDate, setRemindStartDate] = useState(initial?.remind_start_date ?? todayIsoDate());
  const [remindEndDate, setRemindEndDate] = useState(initial?.remind_end_date ?? initial?.remind_start_date ?? todayIsoDate());
  const [saving, setSaving] = useState(false); const [error, setError] = useState<string | null>(null);
  const mutationInFlight = useRef(false);

  const validate = (): string | null => {
    if (!content.trim()) return "請輸入待辦內容";
    if (!/^\d{4}-\d{2}-\d{2}$/.test(remindStartDate) || !/^\d{4}-\d{2}-\d{2}$/.test(remindEndDate)) return "請選擇提醒日期";
    if (remindEndDate < remindStartDate) return "提醒結束日期不可早於開始日期";
    return null;
  };

  const save = async () => {
    const validationError = validate();
    if (validationError) { setError(validationError); return; }
    if (mutationInFlight.current) return;
    mutationInFlight.current = true;
    setSaving(true); setError(null);
    const payload = { content: content.trim(), remind_start_date: remindStartDate, remind_end_date: remindEndDate };
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
    <TodoCalendarPicker endDate={remindEndDate} onChange={(range) => { setRemindStartDate(range.start); setRemindEndDate(range.end); }} startDate={remindStartDate} />
    <View style={styles.field}><Text style={styles.label}>內容</Text><TextInput multiline onChangeText={setContent} placeholder="請輸入待辦內容" placeholderTextColor={colors.textMuted} style={[styles.input, styles.multiline, styles.iosInputFontSize]} value={content} /></View>
    {error ? <Text style={styles.message}>{error}</Text> : null}
    <View style={styles.actions}><Pressable onPress={onClose} style={styles.cancel}><Text style={styles.cancelText}>取消</Text></Pressable><Pressable disabled={saving} onPress={() => void save()} style={styles.save}><Text style={styles.saveText}>{saving ? "儲存中…" : "確認"}</Text></Pressable></View>
  </ScrollView></View></View></Modal>;
}

const createStyles = (colors: ReturnType<typeof useAppPreferences>["colors"], theme: ReturnType<typeof useAppPreferences>["theme"]) => StyleSheet.create({
  flex: { flex: 1 }, intro: { alignItems: "flex-start", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 18, borderWidth: 1, flexDirection: "row", gap: 12, padding: 18 }, introTitle: { color: colors.text, fontSize: 20, fontWeight: "900" }, description: { color: colors.textMuted, fontSize: 12, lineHeight: 18, marginTop: 5 }, addButton: { alignItems: "center", alignSelf: "flex-start", backgroundColor: colors.primary, borderRadius: 11, flexDirection: "row", gap: 7, paddingHorizontal: 16, paddingVertical: 11 }, addText: { color: theme === "dark" ? colors.background : colors.white, fontWeight: "900" },
  message: { color: colors.danger, fontWeight: "700", textAlign: "center" }, empty: { color: colors.textMuted, padding: 24, textAlign: "center" }, card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 16, borderWidth: 1, gap: 8, padding: 17 }, cardHeading: { alignItems: "flex-start", flexDirection: "row", gap: 10, justifyContent: "space-between" }, cardTitle: { color: colors.text, flex: 1, fontSize: 16, fontWeight: "900" }, meta: { color: colors.textMuted, fontSize: 12, fontWeight: "700" },
  actions: { flexDirection: "row", gap: 8, justifyContent: "flex-end" }, edit: { backgroundColor: colors.primarySoft, borderRadius: 9, paddingHorizontal: 14, paddingVertical: 8 }, editText: { color: colors.primaryDark, fontWeight: "800" }, delete: { backgroundColor: theme === "dark" ? "#432823" : "#FAD7D5", borderRadius: 9, paddingHorizontal: 14, paddingVertical: 8 }, deleteText: { color: colors.danger, fontWeight: "800" }, readOnly: { color: colors.textMuted, fontSize: 11 },
  modalRoot: { alignItems: "center", flex: 1, justifyContent: "center", padding: 18 }, backdrop: { backgroundColor: "rgba(18,35,32,.5)", bottom: 0, left: 0, position: "absolute", right: 0, top: 0 }, modalCard: { backgroundColor: colors.surface, borderRadius: 20, maxHeight: "94%", maxWidth: 480, width: "100%" }, close: { padding: 12, position: "absolute", right: 4, top: 4, zIndex: 2 }, modalContent: { gap: 13, padding: 22, paddingTop: 45 }, modalTitle: { color: colors.text, fontSize: 22, fontWeight: "900" },
  field: { gap: 7 }, label: { color: colors.text, fontSize: 14, fontWeight: "800" }, input: { backgroundColor: theme === "dark" ? "#22332F" : colors.white, borderColor: colors.border, borderRadius: 11, borderWidth: 1, color: colors.text, padding: 12 }, multiline: { minHeight: 90, textAlignVertical: "top" }, iosInputFontSize: { fontSize: 16 },
  cancel: { borderColor: colors.border, borderRadius: 10, borderWidth: 1, paddingHorizontal: 18, paddingVertical: 10 }, cancelText: { color: colors.textMuted, fontWeight: "800" }, save: { backgroundColor: colors.primary, borderRadius: 10, paddingHorizontal: 20, paddingVertical: 10 }, saveText: { color: theme === "dark" ? colors.background : colors.white, fontWeight: "900" },
  deleteBackdrop: { alignItems: "center", backgroundColor: "rgba(18,35,32,.5)", flex: 1, justifyContent: "center", padding: 20 }, deleteCard: { backgroundColor: colors.surface, borderRadius: 20, gap: 14, maxWidth: 420, padding: 24, width: "100%" }, deleteTitle: { color: colors.text, fontSize: 20, fontWeight: "900" }, deleteBody: { color: colors.text, fontSize: 13, lineHeight: 20 },
  undoBar: { alignItems: "center", alignSelf: "center", backgroundColor: colors.primaryDark, borderRadius: 20, bottom: 22, flexDirection: "row", gap: 14, paddingHorizontal: 18, paddingVertical: 10, position: "absolute", zIndex: 20 },
  undoMessage: { color: colors.white, fontWeight: "800" },
  undoAction: { color: "#FFD18A", fontWeight: "900", textDecorationLine: "underline" },
});
