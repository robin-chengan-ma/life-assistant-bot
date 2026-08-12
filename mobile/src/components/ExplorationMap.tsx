import { StyleSheet } from "react-native";

import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";
import { useAppPreferences } from "@/context/AppPreferencesContext";

export type ExplorationMapMarker = {
  id: string;
  latitude: number;
  longitude: number;
  title: string;
  type: string;
};

export function ExplorationMap({ markers: _markers }: { markers: ExplorationMapMarker[] }) {
  const { colors } = useAppPreferences();
  return (
    <View style={[styles.fallback, { backgroundColor: colors.surface, borderColor: colors.border }]}>
      <Text style={[styles.title, { color: colors.text }]}>探索地圖目前使用 Web 版本</Text>
      <Text style={[styles.description, { color: colors.textMuted }]}>
        正式原生版本需要另行選擇 Apple Maps／Google Maps；現階段 iPhone 與 Android 請透過瀏覽器使用。
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  description: { fontSize: 13, lineHeight: 20, textAlign: "center" },
  fallback: { alignItems: "center", borderRadius: 18, borderWidth: 1, gap: 8, justifyContent: "center", minHeight: 280, padding: 24 },
  title: { fontSize: 18, fontWeight: "900" },
});
