import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";
import { useEffect, useState } from "react";
import { ActivityIndicator, Modal, ScrollView, StyleSheet, TextInput } from "react-native";

import { AppPressable as Pressable } from "@/components/AppPressable";
import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";
import { SearchableSelect } from "@/components/SearchableSelect";
import { useAppPreferences } from "@/context/AppPreferencesContext";
import type { AuthRequest } from "@/services/analyticsApi";
import {
  createCollectionItem,
  geocodeCollectionAddress,
  getCollectionItems,
  type CollectionItem,
  type CollectionItemType,
  type CollectionPayload,
  updateCollectionItem,
} from "@/services/collectionApi";

const TYPE_OPTIONS: Array<[CollectionItemType, string]> = [["restaurant", "餐廳"], ["attraction", "景點"], ["mountain", "山岳"], ["accommodation", "住宿"], ["activity", "活動"], ["other", "其他"]];

type Props = {
  authorizedRequest: AuthRequest;
  initial?: CollectionItem | null;
  onClose: () => void;
  onSaved: (message: string) => void | Promise<void>;
  visible: boolean;
};

export function CollectionModal({ authorizedRequest, initial = null, onClose, onSaved, visible }: Props) {
  const { colors, theme } = useAppPreferences();
  const styles = createStyles(colors, theme);
  const [title, setTitle] = useState("");
  const [itemType, setItemType] = useState<CollectionItemType>("restaurant");
  const [countryName, setCountryName] = useState("");
  const [cityName, setCityName] = useState("");
  const [address, setAddress] = useState("");
  const [latitude, setLatitude] = useState<number | null>(null);
  const [longitude, setLongitude] = useState<number | null>(null);
  const [locationLabel, setLocationLabel] = useState<string | null>(null);
  const [sourceUrl, setSourceUrl] = useState("");
  const [estimatedCost, setEstimatedCost] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [locating, setLocating] = useState(false);
  const [locationOptions, setLocationOptions] = useState<{ countries: string[]; items: CollectionItem[] }>({ countries: [], items: [] });

  useEffect(() => { if (visible) void getCollectionItems(authorizedRequest).then((result) => setLocationOptions({ countries: result.filters.countries, items: result.items })).catch(() => undefined); }, [authorizedRequest, visible]);

  useEffect(() => {
    if (!visible) return;
    setTitle(initial?.title ?? "");
    setItemType(initial?.item_type ?? "restaurant");
    setCountryName(initial?.country_name ?? "");
    setCityName(initial?.city_name ?? "");
    setAddress(initial?.address ?? "");
    setLatitude(initial?.latitude ?? null);
    setLongitude(initial?.longitude ?? null);
    setLocationLabel(initial?.latitude !== null && initial?.longitude !== null ? "已完成地址定位" : null);
    setSourceUrl(initial?.source_url ?? "");
    setEstimatedCost(initial?.estimated_cost?.toString() ?? "");
    setNotes(initial?.notes ?? "");
    setError(null);
  }, [initial, visible]);

  const invalidateLocation = (value: string) => {
    setAddress(value);
    setLatitude(null);
    setLongitude(null);
    setLocationLabel(null);
  };

  const invalidateCountry = (value: string) => {
    setCountryName(value);
    setCityName("");
    setLatitude(null);
    setLongitude(null);
    setLocationLabel(null);
  };

  const invalidateCity = (value: string) => {
    setCityName(value);
    setLatitude(null);
    setLongitude(null);
    setLocationLabel(null);
  };

  const locateAddress = async () => {
    if (!countryName.trim()) { setError("請先輸入國家"); return; }
    if (!cityName.trim()) { setError("請先輸入區域／城市"); return; }
    setLocating(true); setError(null);
    try {
      const result = await geocodeCollectionAddress(authorizedRequest, {
        address: address.trim() || undefined, city_name: cityName.trim(), country_name: countryName.trim(),
      });
      setLatitude(result.latitude); setLongitude(result.longitude);
      setLocationLabel(`${result.precision_label}：${result.display_name}`);
    } catch (caught) {
      setLatitude(null); setLongitude(null); setLocationLabel(null);
      setError(caught instanceof Error ? caught.message : "地址定位失敗，請稍後重試");
    } finally { setLocating(false); }
  };

  const submit = async () => {
    if (!title.trim()) { setError("請輸入收藏名稱"); return; }
    if (!countryName.trim()) { setError("請輸入國家"); return; }
    if (!cityName.trim()) { setError("請輸入區域／城市"); return; }
    const cost = estimatedCost.trim() ? Number(estimatedCost) : undefined;
    if (cost !== undefined && (!Number.isFinite(cost) || cost < 0)) { setError("請輸入正確的預估費用"); return; }
    const payload: CollectionPayload = {
      item_type: itemType,
      title: title.trim(),
      country_name: countryName.trim() || undefined,
      city_name: cityName.trim() || undefined,
      address: address.trim() || undefined,
      latitude: latitude ?? undefined,
      longitude: longitude ?? undefined,
      source_url: sourceUrl.trim() || undefined,
      estimated_cost: cost,
      currency_code: "TWD",
      notes: notes.trim() || undefined,
    };
    setSaving(true); setError(null);
    try {
      const result = initial
        ? await updateCollectionItem(authorizedRequest, initial.id, payload)
        : await createCollectionItem(authorizedRequest, payload);
      await onSaved(result.message);
      onClose();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "收藏項目儲存失敗，請重試");
    } finally { setSaving(false); }
  };

  return <Modal animationType="fade" onRequestClose={onClose} transparent visible={visible}>
    <View style={styles.backdrop}>
      <View style={styles.card}>
        <Pressable accessibilityLabel="關閉" onPress={onClose} style={styles.close}><MaterialCommunityIcons color={colors.textMuted} name="close" size={26} /></Pressable>
        <Text style={styles.title}>{initial ? "編輯收藏" : "新增收藏"}</Text>
        <ScrollView contentContainerStyle={styles.form} keyboardShouldPersistTaps="handled">
          <Text style={styles.locationNotice}>目前定位功能以「行政區／鄉鎮市區」為主，有時候可能無法精確辨識至門牌或街道。</Text>
          <Field label="收藏名稱" onChangeText={setTitle} placeholder="請輸入收藏名稱" styles={styles} value={title} />
          <ChoiceRow label="類型" onChange={setItemType} options={TYPE_OPTIONS} styles={styles} value={itemType} />
          <SearchableSelect label="國家" onChange={invalidateCountry} options={locationOptions.countries} placeholder="搜尋或輸入國家" value={countryName} />
          <SearchableSelect label="區域／城市" onChange={invalidateCity} options={[...new Set(locationOptions.items.filter((item) => !countryName || item.country_name === countryName).map((item) => item.city_name).filter((value): value is string => Boolean(value)))]} placeholder="搜尋或輸入區域／城市" value={cityName} />
          <Field label="地址（選填）" onChangeText={invalidateLocation} placeholder="可輸入詳細地址以提高定位精度" styles={styles} value={address} />
          <View style={styles.locationRow}><Pressable disabled={locating || saving} onPress={() => void locateAddress()} style={styles.locate}>{locating ? <ActivityIndicator color={colors.primaryDark} /> : <><MaterialCommunityIcons color={colors.primaryDark} name="map-marker-check-outline" size={18} /><Text style={styles.locateText}>{latitude !== null ? "重新定位" : address.trim() ? "定位地址" : "定位區域"}</Text></>}</Pressable>{locationLabel ? <Text style={styles.locationText}>{locationLabel}</Text> : <Text style={styles.locationHint}>尚未執行定位；未定位仍可儲存</Text>}</View>
          <Field autoCapitalize="none" keyboardType="url" label="參考網址" onChangeText={setSourceUrl} placeholder="https://" styles={styles} value={sourceUrl} />
          <Field keyboardType="decimal-pad" label="預估費用（台幣）" onChangeText={(value) => setEstimatedCost(value.replace(/[^0-9.]/g, ""))} placeholder="請輸入數字" styles={styles} value={estimatedCost} />
          <Field label="備註" multiline onChangeText={setNotes} placeholder="可填寫推薦原因、必吃菜色或其他說明" styles={styles} value={notes} />
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <View style={styles.actions}><Pressable disabled={saving} onPress={onClose} style={styles.cancel}><Text style={styles.cancelText}>取消</Text></Pressable><Pressable disabled={saving} onPress={() => void submit()} style={styles.submit}>{saving ? <ActivityIndicator color={theme === "dark" ? colors.background : colors.white} /> : <Text style={styles.submitText}>確認</Text>}</Pressable></View>
        </ScrollView>
      </View>
    </View>
  </Modal>;
}

function Field({ label, styles, multiline = false, ...props }: React.ComponentProps<typeof TextInput> & { label: string; styles: ReturnType<typeof createStyles> }) {
  return <View style={styles.field}><Text style={styles.label}>{label}</Text><TextInput multiline={multiline} placeholderTextColor={styles.placeholder.color} style={[styles.input, multiline && styles.multiline]} {...props} /></View>;
}

function ChoiceRow<T extends string>({ label, onChange, options, styles, value }: { label: string; onChange: (value: T) => void; options: Array<readonly [T, string]>; styles: ReturnType<typeof createStyles>; value: T }) {
  return <View style={styles.field}><Text style={styles.label}>{label}</Text><View style={styles.choices}>{options.map(([key, text]) => <Pressable key={key} onPress={() => onChange(key)} style={[styles.choice, value === key && styles.choiceActive]}><Text style={[styles.choiceText, value === key && styles.choiceTextActive]}>{text}</Text></Pressable>)}</View></View>;
}

const createStyles = (colors: ReturnType<typeof useAppPreferences>["colors"], theme: ReturnType<typeof useAppPreferences>["theme"]) => StyleSheet.create({
  backdrop: { alignItems: "center", backgroundColor: "rgba(13,30,27,0.55)", flex: 1, justifyContent: "center", padding: 18 },
  card: { backgroundColor: colors.surface, borderRadius: 20, maxHeight: "92%", maxWidth: 680, paddingHorizontal: 20, paddingTop: 54, position: "relative", width: "100%" },
  close: { alignItems: "center", height: 40, justifyContent: "center", position: "absolute", right: 12, top: 10, width: 40, zIndex: 2 },
  title: { color: colors.text, fontSize: 22, fontWeight: "900", marginBottom: 14 },
  form: { gap: 15, paddingBottom: 28 }, field: { gap: 7, width: "100%" }, label: { color: colors.text, fontSize: 14, fontWeight: "800" },
  input: { backgroundColor: theme === "dark" ? colors.background : colors.surface, borderColor: colors.border, borderRadius: 11, borderWidth: 1, color: colors.text, fontSize: 16, paddingHorizontal: 13, paddingVertical: 11 },
  multiline: { minHeight: 90, textAlignVertical: "top" }, placeholder: { color: colors.textMuted },
  choices: { flexDirection: "row", flexWrap: "wrap", gap: 8 }, choice: { backgroundColor: colors.primarySoft, borderColor: colors.border, borderRadius: 16, borderWidth: 1, paddingHorizontal: 12, paddingVertical: 7 },
  choiceActive: { backgroundColor: colors.primary, borderColor: colors.primary }, choiceText: { color: colors.primaryDark, fontSize: 13, fontWeight: "700" }, choiceTextActive: { color: theme === "dark" ? colors.background : colors.white },
  error: { color: colors.danger, fontSize: 13, fontWeight: "700" }, actions: { backgroundColor: colors.surface, flexDirection: "row", gap: 10, justifyContent: "flex-end", marginTop: 4, paddingTop: 4 },
  locationNotice: { backgroundColor: colors.primarySoft, borderRadius: 10, color: colors.textMuted, fontSize: 12, lineHeight: 19, padding: 11 },
  locationRow: { alignItems: "flex-start", gap: 7 }, locate: { alignItems: "center", alignSelf: "flex-start", backgroundColor: colors.primarySoft, borderRadius: 10, flexDirection: "row", gap: 7, paddingHorizontal: 13, paddingVertical: 9 }, locateText: { color: colors.primaryDark, fontWeight: "800" }, locationText: { color: colors.primaryDark, fontSize: 12, lineHeight: 18 }, locationHint: { color: colors.textMuted, fontSize: 12 },
  cancel: { backgroundColor: colors.primarySoft, borderRadius: 10, paddingHorizontal: 20, paddingVertical: 11 }, cancelText: { color: colors.text, fontWeight: "800" }, submit: { alignItems: "center", backgroundColor: colors.primary, borderRadius: 10, minWidth: 92, paddingHorizontal: 20, paddingVertical: 11 }, submitText: { color: theme === "dark" ? colors.background : colors.white, fontWeight: "800" },
});
