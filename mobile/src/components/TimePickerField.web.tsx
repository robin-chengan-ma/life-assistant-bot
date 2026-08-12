import { type ChangeEvent, createElement } from "react";
import { StyleSheet } from "react-native";

import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";
import { useAppPreferences } from "@/context/AppPreferencesContext";

export function TimePickerField({ onChange, value }: { onChange: (value: string) => void; value: string }) {
  const { colors, theme } = useAppPreferences();
  const styles = createStyles(colors);
  const webInputStyle = {
    backgroundColor: theme === "dark" ? "#22332F" : colors.white,
    border: `1px solid ${colors.border}`,
    borderRadius: 11,
    color: colors.text,
    colorScheme: theme,
    fontFamily: "inherit",
    fontSize: 15,
    padding: 12,
  };
  return <View style={styles.field}>
    <Text style={styles.label}>執行時間</Text>
    {createElement("input", {
      "aria-label": "執行時間",
      onChange: (event: ChangeEvent<HTMLInputElement>) => onChange(event.target.value),
      style: webInputStyle,
      type: "time",
      value,
    })}
  </View>;
}

const createStyles = (colors: ReturnType<typeof useAppPreferences>["colors"]) => StyleSheet.create({
  field: { gap: 7 },
  label: { color: colors.text, fontSize: 14, fontWeight: "800" },
});
