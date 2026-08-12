import { Text as NativeText, type TextProps, StyleSheet, type TextStyle } from "react-native";

import { lightColors, type AppColors } from "@/constants/theme";
import { useAppPreferences } from "@/context/AppPreferencesContext";

const COLOR_KEYS = Object.keys(lightColors) as Array<keyof AppColors>;

export function AppText({ style, ...props }: TextProps) {
  const { colors, fontScale } = useAppPreferences();
  const flattened = StyleSheet.flatten(style) ?? {};
  const themedStyle: TextStyle = { ...flattened };

  if (typeof flattened.fontSize === "number") themedStyle.fontSize = flattened.fontSize * fontScale;
  if (typeof flattened.lineHeight === "number") themedStyle.lineHeight = flattened.lineHeight * fontScale;
  const colorKey = COLOR_KEYS.find((key) => lightColors[key] === flattened.color);
  if (colorKey) themedStyle.color = colors[colorKey];
  const backgroundKey = COLOR_KEYS.find((key) => lightColors[key] === flattened.backgroundColor);
  if (backgroundKey) themedStyle.backgroundColor = colors[backgroundKey];

  return <NativeText {...props} style={themedStyle} />;
}
