import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";
import { Redirect } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, Alert, Modal, ScrollView, StyleSheet, TextInput } from "react-native";

import { AppPressable as Pressable } from "@/components/AppPressable";
import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";
import { AppShell } from "@/components/AppShell";
import { useAppPreferences } from "@/context/AppPreferencesContext";
import { useAuth } from "@/context/AuthContext";
import {
  createBirthday,
  deleteBirthday,
  getBirthdays,
  updateBirthday,
  type Birthday,
} from "@/services/analyticsApi";

// 生日設定：僅支援每年循環的生日提醒（姓名＋月/日），不含旅遊／目標等其他事件概念。
export default function BirthdaysScreen() {
  const { authorizedRequest, status } = useAuth();
  const { colors, theme } = useAppPreferences();
  const styles = createStyles(colors, theme);
  const [items, setItems] = useState<Birthday[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [operationMessage, setOperationMessage] = useState<string | null>(null);
  const [editing, setEditing] = useState<Birthday | null | undefined>(undefined);
  const [pendingDeletion, setPendingDeletion] = useState<Birthday | null>(null);
  const deleteTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    if (status !== "authenticated") return;
    setLoading(true); setMessage(null);
    try { const result = await getBirthdays(authorizedRequest); setItems(result.items); }
    catch (error) { setMessage(error instanceof Error ? error.message : "目前無法連接資料服務，請稍後再試"); }
    finally { setLoading(false); }
  }, [authorizedRequest, status]);
  useEffect(() => { void load(); }, [load]);

  const scheduleDelete = (item: Birthday) => {
    if (pendingDeletion) return;
    setPendingDeletion(item); setOperationMessage("已排定刪除，5 秒內可復原");
    deleteTimer.current = setTimeout(() => {
      void deleteBirthday(authorizedRequest, item.id)
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

  const sorted = items.slice().sort((left, right) => left.birth_month - right.birth_month || left.birth_day - right.birth_day);

  if (status === "guest") return <Redirect href="/login" />;
  if (loading && !items.length && !message) return <AppShell title="生日設定"><View style={{ alignItems: "center", gap: 12, justifyContent: "center", minHeight: 360 }}><ActivityIndicator color={colors.primary} size="large" /><Text style={{ color: colors.textMuted, fontWeight: "700" }}>資料載入中…</Text></View></AppShell>;
  return <AppShell title="生日設定">
    <View style={styles.intro}><MaterialCommunityIcons color={colors.primary} name="cake-variant-outline" size={28} /><View style={styles.flex}><Text style={styles.introTitle}>管理生日提醒</Text><Text style={styles.description}>每年到了生日當天會自動提醒家人；僅需姓名與月/日。</Text></View></View>
    <Pressable onPress={() => setEditing(null)} style={styles.addButton}><MaterialCommunityIcons color={theme === "dark" ? colors.background : colors.white} name="plus" size={20} /><Text style={styles.addText}>新增生日</Text></Pressable>
    {loading ? <ActivityIndicator color={colors.primary} /> : null}
    {message ? <Text style={styles.message}>{message}</Text> : null}
    {!loading && !sorted.length ? <Text style={styles.empty}>目前沒有設定任何生日</Text> : null}
    {sorted.map((item) => <View key={item.id} style={styles.card}>
      <View style={styles.cardHeading}><Text style={styles.cardTitle}>{item.name}</Text><Text style={styles.meta}>{item.birth_month} 月 {item.birth_day} 日</Text></View>
      {item.can_edit ? <View style={styles.actions}><Pressable onPress={() => setEditing(item)} style={styles.edit}><Text style={styles.editText}>編輯</Text></Pressable><Pressable onPress={() => Alert.alert("確認刪除？", "確認後有 5 秒可以復原。", [{ text: "取消" }, { text: "刪除", style: "destructive", onPress: () => scheduleDelete(item) }])} style={styles.delete}><Text style={styles.deleteText}>刪除</Text></Pressable></View> : <Text style={styles.readOnly}>由其他家人建立，僅能查看。</Text>}
    </View>)}
    {editing !== undefined ? <BirthdayModal initial={editing} onClose={() => setEditing(undefined)} onSaved={async () => { setEditing(undefined); setOperationMessage(editing ? "生日已更新" : "生日已儲存"); await load(); }} request={authorizedRequest} /> : null}
    {pendingDeletion ? <View accessibilityLiveRegion="polite" style={styles.undoBar}><Text style={styles.undoMessage}>已排定刪除「{pendingDeletion.name}」</Text><Pressable onPress={undoDelete}><Text style={styles.undoAction}>復原</Text></Pressable></View> : null}
    {operationMessage && !pendingDeletion ? <View accessibilityLiveRegion="polite" style={styles.undoBar}><Text style={styles.undoMessage}>{operationMessage}</Text></View> : null}
  </AppShell>;
}

function BirthdayModal({ initial, onClose, onSaved, request }: { initial: Birthday | null; onClose: () => void; onSaved: () => Promise<void>; request: ReturnType<typeof useAuth>["authorizedRequest"] }) {
  const { colors, theme } = useAppPreferences(); const styles = createStyles(colors, theme);
  const [name, setName] = useState(initial?.name ?? "");
  const [month, setMonth] = useState(String(initial?.birth_month ?? ""));
  const [day, setDay] = useState(String(initial?.birth_day ?? ""));
  const [saving, setSaving] = useState(false); const [error, setError] = useState<string | null>(null);
  const mutationInFlight = useRef(false);

  const validate = (): string | null => {
    if (!name.trim()) return "請輸入姓名";
    const monthValue = Number(month); const dayValue = Number(day);
    if (!Number.isInteger(monthValue) || monthValue < 1 || monthValue > 12) return "月份請輸入 1 到 12";
    if (!Number.isInteger(dayValue) || dayValue < 1 || dayValue > 31) return "日期請輸入 1 到 31";
    return null;
  };

  const save = async () => {
    const validationError = validate();
    if (validationError) { setError(validationError); return; }
    if (mutationInFlight.current) return;
    mutationInFlight.current = true;
    setSaving(true); setError(null);
    const payload = { name: name.trim(), birth_month: Number(month), birth_day: Number(day) };
    try {
      if (initial) await updateBirthday(request, initial.id, payload);
      else await createBirthday(request, payload);
      await onSaved();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "儲存失敗，請確認網路後重試");
    } finally {
      mutationInFlight.current = false;
      setSaving(false);
    }
  };

  return <Modal animationType="fade" transparent visible onRequestClose={onClose}><View style={styles.modalRoot}><Pressable onPress={onClose} style={styles.backdrop} /><View style={styles.modalCard}><Pressable onPress={onClose} style={styles.close}><MaterialCommunityIcons color={colors.textMuted} name="close" size={24} /></Pressable><ScrollView contentContainerStyle={styles.modalContent}>
    <Text style={styles.modalTitle}>{initial ? "編輯生日" : "新增生日"}</Text>
    <Field label="姓名" value={name} onChange={setName} placeholder="請輸入姓名" />
    <View style={styles.row}><Field inputMode="numeric" label="月" value={month} onChange={(value) => setMonth(value.replace(/\D/g, ""))} placeholder="1-12" /><Field inputMode="numeric" label="日" value={day} onChange={(value) => setDay(value.replace(/\D/g, ""))} placeholder="1-31" /></View>
    {error ? <Text style={styles.message}>{error}</Text> : null}
    <View style={styles.actions}><Pressable onPress={onClose} style={styles.cancel}><Text style={styles.cancelText}>取消</Text></Pressable><Pressable disabled={saving} onPress={() => void save()} style={styles.save}><Text style={styles.saveText}>{saving ? "儲存中…" : "確認"}</Text></Pressable></View>
  </ScrollView></View></View></Modal>;
}

function Field({ inputMode, label, onChange, placeholder, value }: { inputMode?: "numeric"; label: string; onChange: (value: string) => void; placeholder: string; value: string }) { const { colors, theme } = useAppPreferences(); const styles = createStyles(colors, theme); return <View style={styles.field}><Text style={styles.label}>{label}</Text><TextInput inputMode={inputMode} onChangeText={onChange} placeholder={placeholder} placeholderTextColor={colors.textMuted} style={[styles.input, styles.iosInputFontSize]} value={value} /></View>; }

const createStyles = (colors: ReturnType<typeof useAppPreferences>["colors"], theme: ReturnType<typeof useAppPreferences>["theme"]) => StyleSheet.create({
  flex: { flex: 1 }, intro: { alignItems: "flex-start", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 18, borderWidth: 1, flexDirection: "row", gap: 12, padding: 18 }, introTitle: { color: colors.text, fontSize: 20, fontWeight: "900" }, description: { color: colors.textMuted, fontSize: 12, lineHeight: 18, marginTop: 5 }, addButton: { alignItems: "center", alignSelf: "flex-start", backgroundColor: colors.primary, borderRadius: 11, flexDirection: "row", gap: 7, paddingHorizontal: 16, paddingVertical: 11 }, addText: { color: theme === "dark" ? colors.background : colors.white, fontWeight: "900" },
  message: { color: colors.danger, fontWeight: "700", textAlign: "center" }, empty: { color: colors.textMuted, padding: 24, textAlign: "center" }, card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 16, borderWidth: 1, gap: 8, padding: 17 }, cardHeading: { alignItems: "center", flexDirection: "row", gap: 10, justifyContent: "space-between" }, cardTitle: { color: colors.text, fontSize: 17, fontWeight: "900" }, meta: { color: colors.textMuted, fontSize: 13, fontWeight: "700" },
  actions: { flexDirection: "row", gap: 8, justifyContent: "flex-end" }, edit: { backgroundColor: colors.primarySoft, borderRadius: 9, paddingHorizontal: 14, paddingVertical: 8 }, editText: { color: colors.primaryDark, fontWeight: "800" }, delete: { backgroundColor: theme === "dark" ? "#432823" : "#FAD7D5", borderRadius: 9, paddingHorizontal: 14, paddingVertical: 8 }, deleteText: { color: colors.danger, fontWeight: "800" }, readOnly: { color: colors.textMuted, fontSize: 11 },
  modalRoot: { alignItems: "center", flex: 1, justifyContent: "center", padding: 18 }, backdrop: { backgroundColor: "rgba(18,35,32,.5)", bottom: 0, left: 0, position: "absolute", right: 0, top: 0 }, modalCard: { backgroundColor: colors.surface, borderRadius: 20, maxHeight: "94%", maxWidth: 480, width: "100%" }, close: { padding: 12, position: "absolute", right: 4, top: 4, zIndex: 2 }, modalContent: { gap: 13, padding: 22, paddingTop: 45 }, modalTitle: { color: colors.text, fontSize: 22, fontWeight: "900" },
  row: { flexDirection: "row", gap: 12 }, field: { flex: 1, gap: 7 }, label: { color: colors.text, fontSize: 14, fontWeight: "800" }, input: { backgroundColor: theme === "dark" ? "#22332F" : colors.white, borderColor: colors.border, borderRadius: 11, borderWidth: 1, color: colors.text, padding: 12 }, iosInputFontSize: { fontSize: 16 },
  cancel: { borderColor: colors.border, borderRadius: 10, borderWidth: 1, paddingHorizontal: 18, paddingVertical: 10 }, cancelText: { color: colors.textMuted, fontWeight: "800" }, save: { backgroundColor: colors.primary, borderRadius: 10, paddingHorizontal: 20, paddingVertical: 10 }, saveText: { color: theme === "dark" ? colors.background : colors.white, fontWeight: "900" },
  undoBar: { alignItems: "center", alignSelf: "center", backgroundColor: colors.primaryDark, borderRadius: 20, bottom: 22, flexDirection: "row", gap: 14, paddingHorizontal: 18, paddingVertical: 10, position: "absolute", zIndex: 20 },
  undoMessage: { color: colors.white, fontWeight: "800" },
  undoAction: { color: "#FFD18A", fontWeight: "900", textDecorationLine: "underline" },
});
