import { LinearGradient } from "expo-linear-gradient";
import type { PropsWithChildren } from "react";
import { StyleSheet } from "react-native";

import { AppView as View } from "@/components/AppView";
import { useAppPreferences } from "@/context/AppPreferencesContext";

const BACKGROUND_DOTS = Array.from({ length: 180 }, (_, index) => index);

export function AppBackground({ children }: PropsWithChildren) {
  const { colors, theme } = useAppPreferences();
  const styles = createStyles(colors);
  return (
    <LinearGradient
      colors={theme === "dark" ? ["#0D211E", "#1D1B18", "#102521"] : ["#E4F4EF", "#F7F3E8", "#EAF5F2"]}
      end={{ x: 1, y: 1 }}
      start={{ x: 0, y: 0 }}
      style={styles.page}
    >
      <View pointerEvents="none" style={styles.backgroundPattern}>
        {BACKGROUND_DOTS.map((dot) => (
          <View key={dot} style={styles.backgroundDot} />
        ))}
      </View>
      <View pointerEvents="none" style={styles.decorativeCircleTop} />
      <View pointerEvents="none" style={styles.decorativeCircleBottom} />
      <View style={styles.content}>{children}</View>
    </LinearGradient>
  );
}

const createStyles = (colors: ReturnType<typeof useAppPreferences>["colors"]) => StyleSheet.create({
  page: { flex: 1 },
  content: { flex: 1, zIndex: 1 },
  backgroundPattern: {
    alignContent: "space-around",
    bottom: 0,
    columnGap: 24,
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "space-around",
    left: 0,
    opacity: 0.24,
    overflow: "hidden",
    padding: 12,
    position: "absolute",
    right: 0,
    rowGap: 24,
    top: 0,
  },
  backgroundDot: {
    backgroundColor: colors.primary,
    borderRadius: 2,
    height: 3,
    width: 3,
  },
  decorativeCircleTop: {
    borderColor: "rgba(20, 125, 112, 0.10)",
    borderRadius: 130,
    borderWidth: 28,
    height: 260,
    position: "absolute",
    right: -110,
    top: -95,
    width: 260,
  },
  decorativeCircleBottom: {
    borderColor: "rgba(235, 151, 65, 0.10)",
    borderRadius: 110,
    borderWidth: 24,
    bottom: -90,
    height: 220,
    left: -95,
    position: "absolute",
    width: 220,
  },
});
