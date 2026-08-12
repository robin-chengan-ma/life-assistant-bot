import { StyleSheet } from "react-native";

import { AppShell } from "@/components/AppShell";
import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";
import { ExplorationMap, type ExplorationMapMarker } from "@/components/ExplorationMap";
import { useAppPreferences } from "@/context/AppPreferencesContext";

const SAMPLE_MARKERS: ExplorationMapMarker[] = [
  { id: "taipei-restaurant", latitude: 25.033, longitude: 121.5654, title: "台北餐廳紀錄", type: "餐廳" },
  { id: "nantou-mountain", latitude: 23.851, longitude: 120.914, title: "南投登山紀錄", type: "登山" },
  { id: "kaohsiung-spot", latitude: 22.6273, longitude: 120.3014, title: "高雄景點紀錄", type: "景點" },
];

export default function MapPocScreen() {
  const { colors } = useAppPreferences();
  return (
    <AppShell title="探索地圖技術驗證">
      <View style={[styles.notice, { backgroundColor: colors.surface, borderColor: colors.border }]}>
        <Text style={[styles.title, { color: colors.text }]}>Leaflet＋OpenStreetMap POC</Text>
        <Text style={[styles.description, { color: colors.textMuted }]}>
          此頁只驗證 iPhone、Android 瀏覽器的地圖縮放、拖曳、標記與彈出資訊，不代表正式探索資料。
        </Text>
      </View>
      <ExplorationMap markers={SAMPLE_MARKERS} />
    </AppShell>
  );
}

const styles = StyleSheet.create({
  description: { fontSize: 13, lineHeight: 20 },
  notice: { borderRadius: 16, borderWidth: 1, gap: 7, padding: 16 },
  title: { fontSize: 18, fontWeight: "900" },
});
