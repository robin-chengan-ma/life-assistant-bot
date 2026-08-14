import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";
import { useMemo, useState } from "react";
import { Modal, ScrollView, StyleSheet, TextInput } from "react-native";

import { AppPressable as Pressable } from "@/components/AppPressable";
import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";
import { useAppPreferences } from "@/context/AppPreferencesContext";

export function SearchableSelect({ label, onChange, options, placeholder, value }: { label: string; onChange: (value: string) => void; options: string[]; placeholder: string; value: string }) {
  const { colors, theme } = useAppPreferences(); const styles = createStyles(colors, theme);
  const [open, setOpen] = useState(false); const [query, setQuery] = useState(value);
  const matches = useMemo(() => [...new Set(options)].filter((item) => item.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())), [options, query]);
  const choose = (next: string) => { onChange(next.trim()); setQuery(next.trim()); setOpen(false); };
  return <View style={styles.field}><Text style={styles.label}>{label}</Text><Pressable onPress={() => { setQuery(value); setOpen(true); }} style={styles.control}><Text style={value ? styles.value : styles.placeholder}>{value || placeholder}</Text><MaterialCommunityIcons color={colors.textMuted} name="chevron-down" size={22} /></Pressable>
    <Modal animationType="fade" onRequestClose={() => setOpen(false)} transparent visible={open}><View style={styles.backdrop}><View style={styles.card}><Text style={styles.title}>{label}</Text><TextInput autoFocus onChangeText={setQuery} placeholder={placeholder} placeholderTextColor={colors.textMuted} style={styles.input} value={query} /><ScrollView nestedScrollEnabled showsVerticalScrollIndicator style={styles.options}>{matches.map((item) => <Pressable key={item} onPress={() => choose(item)} style={styles.option}><Text style={styles.optionText}>{item}</Text></Pressable>)}</ScrollView><View style={styles.actions}><Pressable onPress={() => setOpen(false)} style={styles.cancel}><Text style={styles.cancelText}>取消</Text></Pressable><Pressable disabled={!query.trim()} onPress={() => choose(query)} style={styles.submit}><Text style={styles.submitText}>{matches.includes(query.trim()) ? "選擇" : "使用新值"}</Text></Pressable></View></View></View></Modal>
  </View>;
}

const createStyles = (colors: ReturnType<typeof useAppPreferences>["colors"], theme: ReturnType<typeof useAppPreferences>["theme"]) => StyleSheet.create({
  field: { gap: 7, width: "100%" }, label: { color: colors.text, fontSize: 14, fontWeight: "800" }, control: { alignItems: "center", backgroundColor: theme === "dark" ? colors.background : colors.surface, borderColor: colors.border, borderRadius: 11, borderWidth: 1, flexDirection: "row", justifyContent: "space-between", paddingHorizontal: 13, paddingVertical: 12 }, value: { color: colors.text, fontSize: 16 }, placeholder: { color: colors.textMuted, fontSize: 16 }, backdrop: { alignItems: "center", backgroundColor: "rgba(13,30,27,.58)", flex: 1, justifyContent: "center", padding: 18 }, card: { backgroundColor: colors.surface, borderRadius: 18, gap: 12, maxWidth: 520, padding: 20, width: "100%" }, title: { color: colors.text, fontSize: 19, fontWeight: "900" }, input: { backgroundColor: theme === "dark" ? colors.background : colors.surface, borderColor: colors.border, borderRadius: 10, borderWidth: 1, color: colors.text, fontSize: 16, padding: 12 }, options: { borderColor: colors.border, borderRadius: 10, borderWidth: 1, maxHeight: 240 }, option: { borderBottomColor: colors.border, borderBottomWidth: 1, padding: 12 }, optionText: { color: colors.text, fontWeight: "700" }, actions: { flexDirection: "row", gap: 9, justifyContent: "flex-end" }, cancel: { backgroundColor: colors.primarySoft, borderRadius: 9, paddingHorizontal: 16, paddingVertical: 10 }, cancelText: { color: colors.text, fontWeight: "800" }, submit: { backgroundColor: colors.primary, borderRadius: 9, paddingHorizontal: 16, paddingVertical: 10 }, submitText: { color: theme === "dark" ? colors.background : colors.white, fontWeight: "900" },
});
