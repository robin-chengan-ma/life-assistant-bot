import { Pressable as NativePressable, type PressableProps, StyleSheet, type ViewStyle } from "react-native";

import { lightColors, type AppColors } from "@/constants/theme";
import { useAppPreferences } from "@/context/AppPreferencesContext";

const COLOR_KEYS = Object.keys(lightColors) as Array<keyof AppColors>;
const COLOR_STYLE_KEYS = ["backgroundColor", "borderColor", "borderTopColor", "borderRightColor", "borderBottomColor", "borderLeftColor", "shadowColor"] as const;

export function AppPressable({ style, ...props }: PressableProps) {
  const { colors } = useAppPreferences();
  const translate = (source: Parameters<typeof StyleSheet.flatten>[0]) => {
    const flattened = (StyleSheet.flatten(source) ?? {}) as ViewStyle;
    const themedStyle: ViewStyle = { ...flattened };
    COLOR_STYLE_KEYS.forEach((styleKey) => {
      const value = flattened[styleKey];
      const colorKey = COLOR_KEYS.find((key) => lightColors[key] === value);
      if (colorKey) themedStyle[styleKey] = colors[colorKey];
    });
    return themedStyle;
  };

  const themedStyle = typeof style === "function"
    ? (state: Parameters<NonNullable<Extract<typeof style, (...args: never[]) => unknown>>>[0]) => translate(style(state))
    : translate(style);
  return <NativePressable {...props} style={themedStyle} />;
}
