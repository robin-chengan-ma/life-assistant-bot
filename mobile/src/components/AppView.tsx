import { View as NativeView, type ViewProps, StyleSheet, type ViewStyle } from "react-native";

import { lightColors, type AppColors } from "@/constants/theme";
import { useAppPreferences } from "@/context/AppPreferencesContext";

const COLOR_KEYS = Object.keys(lightColors) as Array<keyof AppColors>;
const COLOR_STYLE_KEYS = ["backgroundColor", "borderColor", "borderTopColor", "borderRightColor", "borderBottomColor", "borderLeftColor", "shadowColor"] as const;

export function AppView({ style, ...props }: ViewProps) {
  const { colors } = useAppPreferences();
  const flattened = StyleSheet.flatten(style) ?? {};
  const themedStyle: ViewStyle = { ...flattened };

  COLOR_STYLE_KEYS.forEach((styleKey) => {
    const value = flattened[styleKey];
    const colorKey = COLOR_KEYS.find((key) => lightColors[key] === value);
    if (colorKey) themedStyle[styleKey] = colors[colorKey];
  });

  return <NativeView {...props} style={themedStyle} />;
}
