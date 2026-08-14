import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";
import { type Href, Redirect, useRouter } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, Alert, ScrollView, StyleSheet } from "react-native";

import { AppPressable as Pressable } from "@/components/AppPressable";
import { AppShell } from "@/components/AppShell";
import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";
import { SensitiveValue } from "@/components/SensitiveValue";
import { CollectionModal } from "@/components/CollectionModal";
import { useAppPreferences } from "@/context/AppPreferencesContext";
import { useAuth } from "@/context/AuthContext";
import { deleteCollectionItem, getCollectionItems, type CollectionItem, type CollectionItemType, type CollectionResponse, type CollectionStatus } from "@/services/collectionApi";
import { visitCollection } from "@/services/lifeExplorationApi";

const TYPES: Array<[CollectionItemType | "", string]> = [["", "全部類型"], ["restaurant", "餐廳"], ["attraction", "景點"], ["mountain", "山岳"], ["accommodation", "住宿"], ["activity", "活動"], ["other", "其他"]];
const STATUSES: Array<[CollectionStatus | "", string]> = [["", "全部狀態"], ["saved", "已收藏"], ["added_to_trip", "已加入行程"], ["visited", "已造訪"], ["cancelled", "已取消"]];
const TYPE_LABEL = Object.fromEntries(TYPES) as Record<string, string>;
const STATUS_LABEL = Object.fromEntries(STATUSES) as Record<string, string>;

export default function CollectionsScreen() {
  const router = useRouter();
  const { authorizedRequest, status } = useAuth();
  const { colors, theme } = useAppPreferences();
  const styles = createStyles(colors, theme);
  const [data, setData] = useState<CollectionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [type, setType] = useState<CollectionItemType | "">("");
  const [itemStatus, setItemStatus] = useState<CollectionStatus | "">("");
  const [country, setCountry] = useState("");
  const [city, setCity] = useState("");
  const [editing, setEditing] = useState<CollectionItem | null>(null);
  const [pendingDeletion, setPendingDeletion] = useState<CollectionItem | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const deleteTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    if (status !== "authenticated") return;
    setLoading(true); setError(null);
    try { setData(await getCollectionItems(authorizedRequest)); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "收藏清單目前無法載入"); }
    finally { setLoading(false); }
  }, [authorizedRequest, status]);
  useEffect(() => { void load(); }, [load]);

  const scheduleDelete = (item: CollectionItem) => {
    if (deleteTimer.current) return;
    setPendingDeletion(item); setMessage("已排定刪除，5 秒內可復原");
    deleteTimer.current = setTimeout(() => { void deleteCollectionItem(authorizedRequest, item.id).then(load).catch((caught) => setError(caught instanceof Error ? caught.message : "刪除失敗")); deleteTimer.current = null; setPendingDeletion(null); }, 5000);
  };
  const undoDelete = () => { if (deleteTimer.current) clearTimeout(deleteTimer.current); deleteTimer.current = null; setPendingDeletion(null); setMessage("已復原，資料未刪除"); };

  const visibleItems = useMemo(() => (data?.items ?? []).filter((item) =>
    (!type || item.item_type === type)
    && (!itemStatus || item.status === itemStatus)
    && (!country || item.country_name === country)
    && (!city || item.city_name === city),
  ), [city, country, data?.items, itemStatus, type]);

  if (status === "guest") return <Redirect href="/login" />;
  return <AppShell title="收藏清單">
    <View style={styles.intro}><MaterialCommunityIcons color="#D39719" name="bookmark-multiple-outline" size={30} /><View style={styles.flex}><Text style={styles.heading}>想去、想吃、想體驗</Text><Text style={styles.muted}>收藏可組成當天或多日旅遊行程；新增收藏請從首頁進入。</Text></View><Pressable onPress={() => router.push("/trips" as Href)} style={styles.tripButton}><MaterialCommunityIcons color={theme === "dark" ? colors.background : colors.white} name="bag-suitcase-outline" size={18} /><Text style={styles.tripButtonText}>旅遊行程</Text></Pressable></View>
    {message ? <View style={styles.undoBar}><Text style={styles.undoText}>{message}</Text>{pendingDeletion ? <Pressable onPress={undoDelete}><Text style={styles.undoAction}>復原</Text></Pressable> : null}</View> : null}
    {loading ? <ActivityIndicator color={colors.primary} size="large" /> : null}
    {error ? <Pressable onPress={() => void load()} style={styles.error}><Text style={styles.errorText}>{error}</Text><Text style={styles.retry}>點此重試</Text></Pressable> : null}
    {data ? <>
      <View style={styles.summaryRow}><Summary label="全部" styles={styles} value={data.summary.total} /><Summary label="已收藏" styles={styles} value={data.summary.saved} /><Summary label="已加入行程" styles={styles} value={data.summary.added_to_trip} /><Summary label="已造訪" styles={styles} value={data.summary.visited} /></View>
      <FilterRow label="類型" options={TYPES} setValue={(value) => setType(value as CollectionItemType | "")} styles={styles} value={type} />
      <FilterRow label="狀態" options={STATUSES} setValue={(value) => setItemStatus(value as CollectionStatus | "")} styles={styles} value={itemStatus} />
      {data.filters.countries.length ? <FilterRow label="國家" options={[["", "全部國家"], ...data.filters.countries.map((value) => [value, value] as [string, string])]} setValue={setCountry} styles={styles} value={country} /> : null}
      {data.filters.cities.length ? <FilterRow label="城市" options={[["", "全部城市"], ...data.filters.cities.map((value) => [value, value] as [string, string])]} setValue={setCity} styles={styles} value={city} /> : null}
      <View style={styles.list}>{visibleItems.length ? visibleItems.map((item) => <CollectionCard item={item} key={item.id} onDelete={() => Alert.alert("確認刪除？", "確認後有 5 秒可以復原；既有探索歷史不會被刪除。", [{ text: "取消" }, { text: "刪除", style: "destructive", onPress: () => scheduleDelete(item) }])} onEdit={() => setEditing(item)} onVisit={() => Alert.alert("確認已造訪？", "將以今天日期建立探索紀錄。", [{ text: "取消" }, { text: "確認", onPress: () => void visitCollection(authorizedRequest, item.id, new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Taipei" })).then(load).catch((caught) => setError(caught instanceof Error ? caught.message : "操作失敗")) }])} styles={styles} />) : <View style={styles.empty}><MaterialCommunityIcons color={colors.textMuted} name="bookmark-off-outline" size={36} /><Text style={styles.muted}>目前沒有符合條件的收藏項目</Text></View>}</View>
    </> : null}
    {editing ? <CollectionModal authorizedRequest={authorizedRequest} initial={editing} onClose={() => setEditing(null)} onSaved={async (savedMessage) => { setMessage(savedMessage); setEditing(null); await load(); }} visible /> : null}
  </AppShell>;
}

function Summary({ label, styles, value }: { label: string; styles: ReturnType<typeof createStyles>; value: number }) { return <View style={styles.summary}><Text style={styles.summaryValue}>{value}</Text><Text style={styles.muted}>{label}</Text></View>; }

function FilterRow({ label, options, setValue, styles, value }: { label: string; options: Array<readonly [string, string]>; setValue: (value: string) => void; styles: ReturnType<typeof createStyles>; value: string }) {
  return <View style={styles.filterGroup}><Text style={styles.filterLabel}>{label}</Text><ScrollView contentContainerStyle={styles.filters} horizontal showsHorizontalScrollIndicator={false}>{options.map(([key, text]) => <Pressable key={`${label}-${key || "all"}`} onPress={() => setValue(key)} style={[styles.filter, value === key && styles.filterActive]}><Text style={[styles.filterText, value === key && styles.filterTextActive]}>{text}</Text></Pressable>)}</ScrollView></View>;
}

function CollectionCard({ item, onDelete, onEdit, onVisit, styles }: { item: CollectionItem; onDelete: () => void; onEdit: () => void; onVisit: () => void; styles: ReturnType<typeof createStyles> }) {
  const location = [item.country_name, item.city_name].filter(Boolean).join("・");
  return <View style={styles.itemCard}><View style={styles.itemHeading}><View style={styles.typeBadge}><Text style={styles.typeText}>{TYPE_LABEL[item.item_type] ?? "其他"}</Text></View><Text style={styles.itemTitle}>{item.title}</Text><View style={styles.statusBadge}><Text style={styles.statusText}>{STATUS_LABEL[item.status] ?? item.status}</Text></View></View>{location ? <Text style={styles.muted}>{location}</Text> : null}{item.address ? <Text style={styles.muted}>{item.address}</Text> : null}{item.estimated_cost !== null ? <View style={styles.costRow}><Text style={styles.muted}>預估費用：</Text><SensitiveValue style={styles.muted}>{`${item.currency_code} ${item.estimated_cost.toLocaleString()}`}</SensitiveValue></View> : null}{item.notes ? <Text style={styles.notes}>{item.notes}</Text> : null}<View style={styles.itemActions}><Pressable onPress={onEdit} style={styles.editAction}><Text style={styles.editActionText}>編輯</Text></Pressable>{item.status !== "visited" ? <Pressable onPress={onVisit} style={styles.visitAction}><Text style={styles.visitActionText}>標記已造訪</Text></Pressable> : null}<Pressable onPress={onDelete} style={styles.deleteAction}><Text style={styles.deleteActionText}>刪除</Text></Pressable></View></View>;
}

const createStyles = (colors: ReturnType<typeof useAppPreferences>["colors"], theme: ReturnType<typeof useAppPreferences>["theme"]) => StyleSheet.create({
  intro: { alignItems: "flex-start", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 18, borderWidth: 1, flexDirection: "row", flexWrap: "wrap", gap: 13, padding: 18 }, flex: { flex: 1, minWidth: 180 }, heading: { color: colors.text, fontSize: 20, fontWeight: "900" }, muted: { color: colors.textMuted, fontSize: 13, lineHeight: 20 }, tripButton: { alignItems: "center", backgroundColor: colors.primary, borderRadius: 11, flexDirection: "row", gap: 7, paddingHorizontal: 13, paddingVertical: 10 }, tripButtonText: { color: theme === "dark" ? colors.background : colors.white, fontWeight: "800" },
  error: { backgroundColor: theme === "dark" ? "#3D2422" : "#FFF0F0", borderRadius: 13, gap: 4, padding: 14 }, errorText: { color: colors.danger, fontWeight: "700" }, retry: { color: colors.primary, fontSize: 13, fontWeight: "800" },
  summaryRow: { flexDirection: "row", flexWrap: "wrap", gap: 10 }, summary: { alignItems: "center", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 14, borderWidth: 1, flexBasis: 140, flexGrow: 1, padding: 14 }, summaryValue: { color: colors.primaryDark, fontSize: 24, fontWeight: "900" },
  filterGroup: { gap: 7 }, filterLabel: { color: colors.text, fontSize: 14, fontWeight: "800" }, filters: { gap: 8 }, filter: { backgroundColor: colors.primarySoft, borderRadius: 17, paddingHorizontal: 13, paddingVertical: 8 }, filterActive: { backgroundColor: colors.primary }, filterText: { color: colors.primaryDark, fontSize: 13, fontWeight: "700" }, filterTextActive: { color: theme === "dark" ? colors.background : colors.white },
  list: { gap: 11 }, empty: { alignItems: "center", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 16, borderWidth: 1, gap: 8, padding: 28 }, itemCard: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 16, borderWidth: 1, gap: 6, padding: 16 }, itemHeading: { alignItems: "center", flexDirection: "row", flexWrap: "wrap", gap: 8 }, itemTitle: { color: colors.text, flex: 1, fontSize: 16, fontWeight: "900", minWidth: 150 },
  typeBadge: { backgroundColor: theme === "dark" ? "#4B3D1C" : "#FFF2D0", borderRadius: 12, paddingHorizontal: 9, paddingVertical: 5 }, typeText: { color: theme === "dark" ? "#FFD676" : "#8A6010", fontSize: 12, fontWeight: "800" }, statusBadge: { backgroundColor: colors.primarySoft, borderRadius: 12, paddingHorizontal: 9, paddingVertical: 5 }, statusText: { color: colors.primaryDark, fontSize: 12, fontWeight: "800" }, costRow: { alignItems: "center", flexDirection: "row" }, notes: { color: colors.text, fontSize: 14, lineHeight: 21, marginTop: 3 }, itemActions: { flexDirection: "row", flexWrap: "wrap", gap: 8, justifyContent: "flex-end", marginTop: 6 }, editAction: { backgroundColor: colors.primarySoft, borderRadius: 9, paddingHorizontal: 13, paddingVertical: 8 }, editActionText: { color: colors.text, fontWeight: "800" }, visitAction: { backgroundColor: colors.primary, borderRadius: 9, paddingHorizontal: 13, paddingVertical: 8 }, visitActionText: { color: theme === "dark" ? colors.background : colors.white, fontWeight: "800" }, deleteAction: { borderColor: colors.danger, borderRadius: 9, borderWidth: 1, paddingHorizontal: 13, paddingVertical: 8 }, deleteActionText: { color: colors.danger, fontWeight: "800" }, undoBar: { alignItems: "center", backgroundColor: colors.primarySoft, borderRadius: 12, flexDirection: "row", justifyContent: "space-between", padding: 13 }, undoText: { color: colors.text, fontWeight: "700" }, undoAction: { color: colors.primaryDark, fontWeight: "900" },
});
