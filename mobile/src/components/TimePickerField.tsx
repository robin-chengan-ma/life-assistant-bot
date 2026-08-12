import DateTimePicker, { type DateTimePickerEvent } from "@react-native-community/datetimepicker";
import { useState } from "react";
import { Platform, StyleSheet } from "react-native";

import { AppPressable as Pressable } from "@/components/AppPressable";
import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";
import { useAppPreferences } from "@/context/AppPreferencesContext";

export function TimePickerField({ onChange, value }: { onChange: (value: string) => void; value: string }) {
  const { colors, theme } = useAppPreferences();
  const styles = createStyles(colors, theme);
  const [visible, setVisible] = useState(false);
  const [hours, minutes] = value.split(":").map(Number);
  const selectedTime = new Date(2026, 0, 1, Number.isFinite(hours) ? hours : 9, Number.isFinite(minutes) ? minutes : 0);

  const changeTime = (_event: DateTimePickerEvent, selected?: Date) => {
    if (Platform.OS === "android") setVisible(false);
    if (!selected) return;
    onChange(`${String(selected.getHours()).padStart(2, "0")}:${String(selected.getMinutes()).padStart(2, "0")}`);
  };

  return <View style={styles.field}>
    <Text style={styles.label}>執行時間</Text>
    <Pressable onPress={() => setVisible(true)} style={styles.input}><Text style={styles.value}>{value}</Text></Pressable>
    {visible ? <DateTimePicker display="default" is24Hour mode="time" onChange={changeTime} value={selectedTime} /> : null}
  </View>;
}

const createStyles = (
  colors: ReturnType<typeof useAppPreferences>["colors"],
  theme: ReturnType<typeof useAppPreferences>["theme"],
) => StyleSheet.create({
  field: { gap: 7 },
  label: { color: colors.text, fontSize: 14, fontWeight: "800" },
  input: { backgroundColor: theme === "dark" ? "#22332F" : colors.white, borderColor: colors.border, borderRadius: 11, borderWidth: 1, padding: 12 },
  value: { color: colors.text, fontSize: 16 },
});
