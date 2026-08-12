import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";
import * as ImagePicker from "expo-image-picker";
import { useEffect, useMemo, useRef, useState } from "react";
import { Calendar, type DateData } from "react-native-calendars";
import { Image, Modal, ScrollView, StyleSheet, TextInput } from "react-native";

import { AppPressable as Pressable } from "@/components/AppPressable";
import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";
import { TimePickerField } from "@/components/TimePickerField";
import { useAppPreferences } from "@/context/AppPreferencesContext";
import { ApiError } from "@/services/authApi";
import { calculateDietNutrition, createRecord, getAnalytics, recognizeDietPhoto, updateRecord, type AuthRequest, type DietNutrition, type RecordItem, type RecordKind, type TodoAnalytics } from "@/services/analyticsApi";
import { calendarImportantDaySummary, IMPORTANT_DAY_COLOR } from "@/utils/calendarLabels";

const EXPENSE = ["餐飲", "交通", "購物", "居住", "娛樂", "醫療", "其他"];
const INCOME = ["薪資", "獎金", "其他"];
const EXERCISE = ["跑步", "健走", "騎自行車", "游泳", "重訓", "打球", "瑜伽", "其他"];
const MOODS = [
  ["happy_excited", "高興／興奮"], ["calm_relaxed", "平靜／放鬆"], ["neutral", "普通／平淡"],
  ["tired_burned_out", "疲倦／厭世"], ["sad_down", "難過／低落"], ["angry_anxious", "生氣／焦慮"],
] as const;
const TODO_STATUSES = [["pending", "待處理"], ["completed", "已完成"], ["cancelled", "已取消"]] as const;
const TITLE: Record<RecordKind, string> = { todo: "新增待辦", finance: "記錄今日收支", diet: "記錄今日飲食", exercise: "記錄今日運動", weight: "記錄今日體態", mood: "記錄今日心情" };

type Props = {
  authorizedRequest: AuthRequest;
  defaults?: Partial<RecordItem> | null;
  initial?: RecordItem | null;
  kind: RecordKind;
  onClose: () => void;
  onSaved: () => Promise<void> | void;
  visible: boolean;
};

function today(): string { return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Taipei" }); }
function localDate(value: unknown): string { return typeof value === "string" ? new Date(value).toLocaleDateString("en-CA", { timeZone: "Asia/Taipei" }) : today(); }
function localTime(value: unknown): string { return typeof value === "string" ? new Date(value).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Taipei" }) : "09:00"; }

export function RecordModal({ authorizedRequest, defaults, initial, kind, onClose, onSaved, visible }: Props) {
  const { colors, theme } = useAppPreferences();
  const styles = createStyles(colors, theme);
  const editing = Boolean(initial);
  const source = initial ?? defaults ?? null;
  const [step, setStep] = useState<"form" | "confirm" | "duplicate" | "diet-review" | "diet-nutrition">("form");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const mutationInFlight = useRef(false);
  const [date, setDate] = useState(today());
  const [endDate, setEndDate] = useState(today());
  const [dateSelectionStarted, setDateSelectionStarted] = useState(false);
  const [time, setTime] = useState("09:00");
  const [content, setContent] = useState("");
  const [type, setType] = useState<"expense" | "income">("expense");
  const [category, setCategory] = useState("餐飲");
  const [amount, setAmount] = useState("");
  const [activity, setActivity] = useState("跑步");
  const [customActivity, setCustomActivity] = useState("");
  const [duration, setDuration] = useState("");
  const [heartRate, setHeartRate] = useState("");
  const [waterMl, setWaterMl] = useState("");
  const [weight, setWeight] = useState("");
  const [waist, setWaist] = useState("");
  const [height, setHeight] = useState("");
  const [mood, setMood] = useState("happy_excited");
  const [todoStatus, setTodoStatus] = useState("pending");
  const [dietImageUri, setDietImageUri] = useState<string | null>(null);
  const [dietUncertainItems, setDietUncertainItems] = useState<string[]>([]);
  const [dietMergeMode, setDietMergeMode] = useState<"add" | "replace">("replace");
  const [dietNutrition, setDietNutrition] = useState<DietNutrition | null>(null);
  const [calendarMonth, setCalendarMonth] = useState(today().slice(0, 7));
  const [todoCalendar, setTodoCalendar] = useState<Pick<TodoAnalytics, "calendar_counts" | "calendar_days">>({ calendar_counts: {}, calendar_days: {} });

  useEffect(() => {
    if (!visible) return;
    setStep("form"); setError(null); setSaving(false);
    setDate(kind === "todo" ? localDate(initial?.start_at ?? initial?.due_at) : today());
    setEndDate(kind === "todo" ? localDate(initial?.due_at) : today());
    setDateSelectionStarted(false);
    setTime(kind === "todo" ? localTime(initial?.due_at) : "09:00");
    setContent(String(source?.content ?? source?.description ?? ""));
    const initialType = source?.type === "income" ? "income" : "expense";
    setType(initialType); setCategory(String(source?.category ?? (initialType === "income" ? "薪資" : "餐飲")));
    setAmount(source?.amount == null ? "" : String(source.amount));
    const oldActivity = String(source?.activity ?? "跑步");
    setActivity(EXERCISE.includes(oldActivity) ? oldActivity : "其他");
    setCustomActivity(EXERCISE.includes(oldActivity) ? "" : oldActivity);
    setDuration(source?.duration_minutes == null ? "" : String(source.duration_minutes));
    setHeartRate(source?.heart_rate == null ? "" : String(source.heart_rate));
    setWaterMl(source?.water_ml == null ? "" : String(source.water_ml));
    setWeight(source?.weight_kg == null ? "" : String(source.weight_kg));
    setWaist(source?.waist_cm == null ? "" : String(source.waist_cm));
    setHeight(source?.height_cm == null ? "" : String(source.height_cm));
    setMood(String(source?.mood_category ?? "happy_excited"));
    setTodoStatus(String(source?.status ?? "pending"));
    setDietImageUri(null); setDietUncertainItems([]); setDietMergeMode("replace"); setDietNutrition(null);
    setCalendarMonth((kind === "todo" ? localDate(initial?.due_at) : today()).slice(0, 7));
  }, [initial, defaults, kind, source, visible]);

  useEffect(() => {
    if (!visible || kind !== "todo") return;
    const selectedDate = date.slice(0, 7) === calendarMonth ? date : `${calendarMonth}-01`;
    void getAnalytics(authorizedRequest, "todos", { start: selectedDate, end: selectedDate }, { calendarMonth })
      .then((result) => setTodoCalendar({ calendar_counts: result.calendar_counts, calendar_days: result.calendar_days ?? {} }))
      .catch(() => setTodoCalendar({ calendar_counts: {}, calendar_days: {} }));
  }, [authorizedRequest, calendarMonth, date, kind, visible]);

  const categories = type === "expense" ? EXPENSE : INCOME;
  useEffect(() => { if (!categories.includes(category)) setCategory(categories[0]); }, [categories, category]);

  const payload = useMemo<Record<string, unknown>>(() => {
    if (kind === "todo") return { content, start_at: `${date}T${time}:00+08:00`, due_at: `${endDate}T${time}:00+08:00`, status: todoStatus };
    if (kind === "finance") return { type, category, amount: Number(amount) };
    if (kind === "diet") return { description: content, water_ml: waterMl ? Number(waterMl) : null, ...(dietNutrition ? { nutrition: dietNutrition } : {}) };
    if (kind === "exercise") return { activity, custom_activity: customActivity, duration_minutes: Number(duration), heart_rate: heartRate ? Number(heartRate) : null };
    if (kind === "weight") return {
      height_cm: height ? Number(height) : editing ? null : source?.height_cm ?? null,
      weight_kg: weight ? Number(weight) : source?.weight_kg ?? null,
      waist_cm: waist ? Number(waist) : editing ? null : source?.waist_cm ?? null,
    };
    return { mood_category: mood, content };
  }, [activity, amount, category, content, customActivity, date, dietNutrition, duration, editing, endDate, heartRate, height, kind, mood, source, time, todoStatus, type, waist, waterMl, weight]);

  const validate = (): string | null => {
    if (kind === "todo" && (!content.trim() || !/^\d{2}:\d{2}$/.test(time))) return "請完整輸入執行日期、時間與內容";
    if (kind === "finance" && (!amount || !Number.isFinite(Number(amount)) || Number(amount) <= 0)) return "請輸入大於 0 的金額";
    if (kind === "diet" && !content.trim()) return "請輸入今日的飲食內容";
    if (kind === "diet" && waterMl && (!Number.isInteger(Number(waterMl)) || Number(waterMl) <= 0)) return "飲水量只能輸入正整數";
    if (kind === "exercise" && (!duration || Number(duration) <= 0 || (activity === "其他" && !customActivity.trim()))) return "請完整輸入運動類別與持續時間";
    if (kind === "weight" && (payload.weight_kg == null || Number(payload.weight_kg) < 40 || Number(payload.weight_kg) > 150)) return "體重僅能輸入 40.0 到 150.0 公斤";
    if (kind === "weight" && payload.height_cm != null && (Number(payload.height_cm) < 140 || Number(payload.height_cm) > 200)) return "身高僅能輸入 140.0 到 200.0 公分";
    if (kind === "weight" && payload.waist_cm != null && (Number(payload.waist_cm) < 50 || Number(payload.waist_cm) > 150)) return "腰圍僅能輸入 50.0 到 150.0 公分";
    return null;
  };

  const prepare = () => { const message = validate(); setError(message); if (!message) setStep("confirm"); };

  const chooseDietPhoto = async (camera: boolean) => {
    setError(null);
    const permission = camera
      ? await ImagePicker.requestCameraPermissionsAsync()
      : await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      setError(camera ? "請允許相機權限後再拍照" : "請允許照片權限後再選擇圖片");
      return;
    }
    const result = camera
      ? await ImagePicker.launchCameraAsync({ base64: true, mediaTypes: ["images"], quality: 0.65 })
      : await ImagePicker.launchImageLibraryAsync({ base64: true, mediaTypes: ["images"], quality: 0.65 });
    if (result.canceled) return;
    const asset = result.assets[0];
    if (!asset.base64) {
      setError("無法讀取這張圖片，請重新選擇");
      return;
    }
    setSaving(true);
    try {
      const recognized = await recognizeDietPhoto(authorizedRequest, asset.base64, asset.mimeType ?? "image/jpeg");
      setContent(recognized.description);
      setDietUncertainItems(recognized.uncertain_items);
      setDietImageUri(asset.uri);
      setDietNutrition(null);
      setStep("diet-review");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "圖片辨識失敗，請稍後再試");
    } finally {
      setSaving(false);
    }
  };

  const calculatePhotoNutrition = async () => {
    if (!content.trim()) {
      setError("請確認或補充飲食內容");
      return;
    }
    setSaving(true); setError(null);
    try {
      const result = await calculateDietNutrition(authorizedRequest, {
        confirmed_description: content,
        existing_description: editing ? String(source?.description ?? "") : undefined,
        mode: editing ? dietMergeMode : "replace",
      });
      setContent(result.description);
      setDietNutrition(result.nutrition);
      setStep("diet-nutrition");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "營養估算失敗，請稍後再試");
    } finally {
      setSaving(false);
    }
  };
  const save = async (allowDuplicate = false) => {
    if (mutationInFlight.current) return;
    mutationInFlight.current = true;
    setSaving(true); setError(null);
    try {
      if (editing && initial) await updateRecord(authorizedRequest, kind, initial.id, { ...payload, allow_duplicate: allowDuplicate });
      else await createRecord(authorizedRequest, kind, { ...payload, allow_duplicate: allowDuplicate });
      await onSaved(); onClose();
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.code === "DUPLICATE_RECORD") { setStep("duplicate"); setError(null); }
      else { setStep("form"); setError(requestError instanceof Error ? requestError.message : "操作失敗，請稍後再試"); }
    } finally { mutationInFlight.current = false; setSaving(false); }
  };

  const clear = () => { setContent(""); setAmount(""); setDuration(""); setHeartRate(""); setWaterMl(""); setHeight(""); setWeight(""); setWaist(""); setCustomActivity(""); setDietImageUri(null); setDietUncertainItems([]); setDietNutrition(null); setError(null); };
  const confirmText = kind === "todo" ? `${date} ～ ${endDate} ${time}｜${content}｜${TODO_STATUSES.find(([value]) => value === todoStatus)?.[1]}` : kind === "finance" ? `${type === "income" ? "收入" : "支出"}｜${category}｜${Math.round(Number(amount))} 元` : kind === "diet" ? `${content}${waterMl ? `｜飲水 ${waterMl} 毫升` : ""}` : kind === "exercise" ? `${activity === "其他" ? customActivity : activity}｜${duration} 分鐘${heartRate ? `｜心率 ${heartRate}` : ""}` : kind === "weight" ? `身高 ${payload.height_cm ?? source?.height_cm ?? "尚無紀錄"} 公分｜體重 ${payload.weight_kg} 公斤｜腰圍 ${payload.waist_cm ?? source?.waist_cm ?? "尚無紀錄"} 公分` : `${MOODS.find(([code]) => code === mood)?.[1] ?? "心情"}${content ? `｜${content}` : ""}`;

  return <Modal animationType="fade" onRequestClose={onClose} transparent visible={visible}><View style={styles.backdrop}><View style={styles.card}><Pressable accessibilityLabel="關閉" disabled={saving} onPress={onClose} style={styles.close}><MaterialCommunityIcons color={colors.textMuted} name="close" size={25} /></Pressable><ScrollView contentContainerStyle={styles.content}>
    <View style={styles.titleRow}><Text style={styles.title}>{editing ? `編輯${TITLE[kind].replace(/^記錄今日|^新增/, "")}` : TITLE[kind]}</Text></View>
    {step === "form" ? <>
      {kind === "todo" ? <><Text style={styles.label}>日期區間</Text><Text style={styles.hint}>{date} ～ {endDate}（依序點選開始與結束日；只選一天即為單日）</Text><View style={styles.calendar}><Calendar current={date} dayComponent={({ date: calendarDate, state }) => { if (!calendarDate) return null; const inRange = calendarDate.dateString >= date && calendarDate.dateString <= endDate; const isStart = calendarDate.dateString === date; const isEnd = calendarDate.dateString === endDate; const holiday = todoCalendar.calendar_days[calendarDate.dateString]; const count = todoCalendar.calendar_counts[calendarDate.dateString] ?? 0; const importantDaySummary = calendarImportantDaySummary(holiday); const selectDay = () => { if (!dateSelectionStarted) { setDate(calendarDate.dateString); setEndDate(calendarDate.dateString); setDateSelectionStarted(true); } else { if (calendarDate.dateString < date) { setEndDate(date); setDate(calendarDate.dateString); } else setEndDate(calendarDate.dateString); setDateSelectionStarted(false); } }; return <Pressable onPress={selectDay} style={[styles.calendarDay, inRange && styles.calendarRangeDay, isStart && styles.calendarRangeStart, isEnd && styles.calendarRangeEnd]}><Text style={[styles.calendarDayNumber, state === "disabled" && styles.calendarDayDisabled, holiday?.is_holiday && styles.calendarHolidayText, (isStart || isEnd) && styles.calendarDaySelectedText]}>{calendarDate.day}</Text>{count > 0 ? <Text style={styles.calendarCount}>{count}件</Text> : <View style={styles.calendarMetaPlaceholder} />}{holiday?.name ? <Text numberOfLines={1} style={styles.calendarHolidayName}>{holiday.name}</Text> : <View style={styles.calendarHolidayPlaceholder} />}{importantDaySummary ? <Text numberOfLines={1} style={styles.calendarNotificationName}>{importantDaySummary}</Text> : null}</Pressable>; }} onDayPress={(day: DateData) => { if (!dateSelectionStarted) { setDate(day.dateString); setEndDate(day.dateString); setDateSelectionStarted(true); } else { setEndDate(day.dateString >= date ? day.dateString : date); if (day.dateString < date) setDate(day.dateString); setDateSelectionStarted(false); } }} onMonthChange={(month) => setCalendarMonth(month.dateString.slice(0, 7))} theme={{ arrowColor: colors.primary, calendarBackground: colors.surface, dayTextColor: colors.text, monthTextColor: colors.text, textSectionTitleColor: colors.textMuted, textDisabledColor: theme === "dark" ? "#52645F" : "#C4CECB", todayTextColor: colors.danger }} /></View><TimePickerField onChange={setTime} value={time} /><Field label="內容" multiline onChange={setContent} placeholder="請輸入待辦內容" value={content} /><Text style={styles.label}>狀態</Text><Dropdown options={TODO_STATUSES} selected={todoStatus} setSelected={setTodoStatus} /></> : null}
      {kind === "finance" ? <><Text style={styles.label}>類型</Text><Options options={[["expense", "支出"], ["income", "收入"]]} selected={type} setSelected={(value) => setType(value as "expense" | "income")} /><Text style={styles.label}>類別</Text><Options options={categories.map((value) => [value, value])} selected={category} setSelected={setCategory} /><Field inputMode="decimal" label="台幣金額（元）" onChange={(value) => setAmount(value.replace(/[^0-9.]/g, ""))} placeholder="請輸入台幣金額" value={amount} /></> : null}
      {kind === "diet" ? <><Field label="今日的飲食內容" multiline onChange={(value) => { setContent(value); setDietNutrition(null); }} placeholder="請輸入今日的飲食內容..." value={content} /><Field inputMode="numeric" label="飲水量 (毫升)" onChange={(value) => setWaterMl(value.replace(/\D/g, ""))} placeholder="請輸入數字" suffix="毫升" value={waterMl} /><Text style={styles.photoDivider}>或用照片辨識飲食內容</Text><View style={styles.photoActions}><IconButton disabled={saving} icon="camera" label={saving ? "辨識中…" : "拍照"} onPress={() => void chooseDietPhoto(true)} /><IconButton disabled={saving} icon="image-multiple" label="從相簿選擇" onPress={() => void chooseDietPhoto(false)} /></View></> : null}
      {kind === "exercise" ? <><Text style={styles.label}>類別</Text><Options options={EXERCISE.map((value) => [value, value])} selected={activity} setSelected={setActivity} />{activity === "其他" ? <Field label="其他運動名稱" onChange={setCustomActivity} placeholder="請輸入運動名稱" value={customActivity} /> : null}<Field inputMode="numeric" label="持續時間（分鐘）" onChange={(value) => setDuration(value.replace(/\D/g, ""))} placeholder="請輸入數字" value={duration} /><Field inputMode="numeric" label="心率（bpm）" onChange={(value) => setHeartRate(value.replace(/\D/g, ""))} placeholder="請輸入數字" value={heartRate} /></> : null}
      {kind === "weight" ? <><Field inputMode="decimal" label="已量測身高值（公分）" onChange={(value) => setHeight(value.replace(/[^0-9.]/g, ""))} placeholder="填入 140 公分至 200 公分範圍內的數值" value={height} /><Field inputMode="decimal" label="已量測體重值（公斤）" onChange={(value) => setWeight(value.replace(/[^0-9.]/g, ""))} placeholder="填入 40 公斤至 150 公斤範圍內的數值" value={weight} /><Field inputMode="decimal" label="已量測腰圍值（公分）" onChange={(value) => setWaist(value.replace(/[^0-9.]/g, ""))} placeholder="填入 50 公分至 150 公分範圍內的數值" value={waist} /></> : null}
      {kind === "mood" ? <><Text style={styles.label}>類別</Text><Options options={MOODS.map(([code, label]) => [code, label])} selected={mood} setSelected={setMood} /><Field label="有沒有要分享的內容呢？" multiline onChange={setContent} placeholder="有話想說嗎？" value={content} /></> : null}
      {kind !== "todo" ? <Text style={styles.hint}>Mobile App 僅提供今日紀錄；若需回補其他日期，請使用 Telegram。</Text> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}<View style={styles.actions}><Button label="取消" onPress={onClose} secondary /><Button label="清除" onPress={clear} warm /><Button label="確認" onPress={prepare} /></View>
    </> : step === "diet-review" ? <>
      {dietImageUri ? <Image source={{ uri: dietImageUri }} style={styles.dietImage} /> : null}
      <Text style={styles.reviewTitle}>請確認辨識到的飲食內容</Text>
      <Field label="飲食品項、份量與烹調方式" multiline onChange={(value) => { setContent(value); setDietNutrition(null); }} placeholder="請補充遺漏的飲食內容" value={content} />
      {dietUncertainItems.length ? <View style={styles.uncertainBox}><Text style={styles.uncertainTitle}>請特別確認：</Text>{dietUncertainItems.map((item, index) => <Text key={`${index}-${item}`} style={styles.uncertainText}>{`• ${item}`}</Text>)}</View> : <Text style={styles.successText}>已完成初步辨識，請確認有無遺漏。</Text>}
      {editing ? <><Text style={styles.label}>如何處理今日既有紀錄？</Text><Options options={[["add", "新增至原紀錄"], ["replace", "取代原紀錄"]]} selected={dietMergeMode} setSelected={(value) => setDietMergeMode(value as "add" | "replace")} /></> : null}
      <Text style={styles.hint}>確認內容後才會估算熱量與營養成分。</Text>
      {error ? <Text style={styles.error}>{error}</Text> : null}<View style={styles.actions}><Button label="重新選擇" onPress={() => setStep("form")} secondary /><Button disabled={saving} label={saving ? "估算中…" : "內容正確，開始估算"} onPress={() => void calculatePhotoNutrition()} /></View>
    </> : step === "diet-nutrition" && dietNutrition ? <>
      <Text style={styles.reviewTitle}>營養估算結果</Text>
      <View style={styles.nutritionCard}><NutritionRow label="熱量" unit="大卡" value={dietNutrition.estimated_calories} /><NutritionRow label="蛋白質" unit="公克" value={dietNutrition.protein_g} /><NutritionRow label="碳水化合物" unit="公克" value={dietNutrition.carbs_g} /><NutritionRow label="脂肪" unit="公克" value={dietNutrition.fat_g} /></View>
      <Text style={styles.previewDescription}>{content}</Text>{waterMl ? <Text style={styles.previewDescription}>飲水量：{waterMl} 毫升</Text> : null}<Text style={styles.aiNotice}>提醒：此結果為 AI 給出的預估值，未必是最準確的數值喔！</Text>
      {error ? <Text style={styles.error}>{error}</Text> : null}<View style={styles.actions}><Button label="返回修改" onPress={() => { setDietNutrition(null); setStep("diet-review"); }} secondary /><Button disabled={saving} label={saving ? "儲存中…" : editing ? "確認更新" : "確認記錄"} onPress={() => void save()} /></View>
    </> : <><Text style={styles.question}>{step === "duplicate" ? "發現一筆可能重複的紀錄，確定仍要新增嗎？" : `${confirmText}\n是否正確？`}</Text><View style={styles.actions}><Button label="返回修改" onPress={() => setStep("form")} secondary /><Button disabled={saving} label={saving ? "處理中…" : step === "duplicate" ? "仍要新增" : editing ? "確認更新" : "確認記錄"} onPress={() => void save(step === "duplicate")} /></View></>}
    </ScrollView></View></View></Modal>;
}

function Field({ inputMode, label, multiline, onChange, placeholder, suffix, value }: { inputMode?: "decimal" | "numeric"; label: string; multiline?: boolean; onChange: (value: string) => void; placeholder?: string; suffix?: string; value: string }) { const { colors, theme } = useAppPreferences(); const styles = createStyles(colors, theme); return <View style={styles.field}><Text style={styles.label}>{label}</Text><View style={suffix ? styles.inputWithSuffix : undefined}><TextInput inputMode={inputMode} multiline={multiline} onChangeText={onChange} placeholder={placeholder} placeholderTextColor={colors.textMuted} style={[styles.input, suffix && styles.suffixInput, multiline && styles.multiline]} value={value} />{suffix ? <Text style={styles.inputSuffix}>{suffix}</Text> : null}</View></View>; }
function Options({ options, selected, setSelected }: { options: readonly (readonly [string, string])[]; selected: string; setSelected: (value: string) => void }) { const { colors, theme } = useAppPreferences(); const styles = createStyles(colors, theme); return <View style={styles.options}>{options.map(([value, label]) => <Pressable key={value} onPress={() => setSelected(value)} style={[styles.option, selected === value && styles.optionSelected]}><Text style={[styles.optionText, selected === value && styles.optionTextSelected]}>{label}</Text></Pressable>)}</View>; }
function Dropdown({ options, selected, setSelected }: { options: readonly (readonly [string, string])[]; selected: string; setSelected: (value: string) => void }) { const { colors, theme } = useAppPreferences(); const styles = createStyles(colors, theme); const [open, setOpen] = useState(false); const label = options.find(([value]) => value === selected)?.[1] ?? "請選擇"; return <View style={styles.dropdownWrap}><Pressable onPress={() => setOpen((value) => !value)} style={styles.dropdown}><Text style={styles.dropdownText}>{label}</Text><MaterialCommunityIcons color={colors.textMuted} name={open ? "chevron-up" : "chevron-down"} size={22} /></Pressable>{open ? <View style={styles.dropdownMenu}>{options.map(([value, optionLabel]) => <Pressable key={value} onPress={() => { setSelected(value); setOpen(false); }} style={[styles.dropdownItem, value === selected && styles.dropdownItemSelected]}><Text style={styles.dropdownText}>{optionLabel}</Text></Pressable>)}</View> : null}</View>; }
function Button({ disabled, label, onPress, secondary, warm }: { disabled?: boolean; label: string; onPress: () => void; secondary?: boolean; warm?: boolean }) { const { colors, theme } = useAppPreferences(); const styles = createStyles(colors, theme); return <Pressable disabled={disabled} onPress={onPress} style={[styles.button, secondary && styles.secondary, warm && styles.warm, disabled && styles.disabled]}><Text style={[styles.buttonText, (secondary || warm) && styles.darkButtonText]}>{label}</Text></Pressable>; }
function IconButton({ disabled, icon, label, onPress }: { disabled?: boolean; icon: "camera" | "image-multiple"; label: string; onPress: () => void }) { const { colors, theme } = useAppPreferences(); const styles = createStyles(colors, theme); return <Pressable disabled={disabled} onPress={onPress} style={[styles.iconButton, disabled && styles.disabled]}><MaterialCommunityIcons color={theme === "dark" ? colors.background : colors.white} name={icon} size={20} /><Text style={styles.buttonText}>{label}</Text></Pressable>; }
function NutritionRow({ label, unit, value }: { label: string; unit: string; value: number | null }) { const { colors, theme } = useAppPreferences(); const styles = createStyles(colors, theme); return <View style={styles.nutritionRow}><Text style={styles.nutritionLabel}>{label}</Text><Text style={styles.nutritionValue}>{value == null ? "無法估算" : `${value.toFixed(1)} ${unit}`}</Text></View>; }

type ThemeColors = ReturnType<typeof useAppPreferences>["colors"];
type AppTheme = ReturnType<typeof useAppPreferences>["theme"];

const createStyles = (colors: ThemeColors, theme: AppTheme) => StyleSheet.create({
  backdrop: { alignItems: "center", backgroundColor: "rgba(16,38,34,.45)", flex: 1, justifyContent: "center", padding: 18 }, card: { backgroundColor: colors.surface, borderRadius: 22, maxHeight: "92%", maxWidth: 600, paddingTop: 42, position: "relative", width: "100%" }, close: { alignItems: "center", height: 40, justifyContent: "center", position: "absolute", right: 8, top: 6, width: 40, zIndex: 2 }, content: { gap: 14, padding: 24 }, titleRow: { alignItems: "center", flexDirection: "row", gap: 10, justifyContent: "flex-start", width: "100%" }, titleIcon: { height: 38, width: 38 }, title: { color: colors.text, fontSize: 22, fontWeight: "900", textAlign: "left" }, field: { gap: 7 }, label: { color: colors.text, fontSize: 14, fontWeight: "800" }, input: { backgroundColor: theme === "dark" ? "#22332F" : colors.white, borderColor: colors.border, borderRadius: 11, borderWidth: 1, color: colors.text, fontSize: 16, padding: 12 }, inputWithSuffix: { alignItems: "center", flexDirection: "row", gap: 10 }, suffixInput: { flex: 1 }, inputSuffix: { color: colors.text, fontSize: 16, fontWeight: "700" }, multiline: { minHeight: 100, textAlignVertical: "top" }, calendar: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 14, borderWidth: 1, overflow: "hidden" }, options: { flexDirection: "row", flexWrap: "wrap", gap: 8 }, option: { backgroundColor: colors.primarySoft, borderColor: colors.border, borderRadius: 18, borderWidth: 1, paddingHorizontal: 13, paddingVertical: 8 }, optionSelected: { backgroundColor: colors.primary, borderColor: colors.primary }, optionText: { color: colors.primaryDark, fontWeight: "700" }, optionTextSelected: { color: theme === "dark" ? colors.background : colors.white }, hint: { color: colors.textMuted, fontSize: 12, lineHeight: 18, textAlign: "center" }, error: { color: colors.danger, fontWeight: "700", textAlign: "center" }, question: { color: colors.primaryDark, fontSize: 19, fontWeight: "900", lineHeight: 29, textAlign: "center" }, actions: { flexDirection: "row", flexWrap: "wrap", gap: 9, justifyContent: "center" }, button: { alignItems: "center", backgroundColor: colors.primary, borderRadius: 11, minWidth: 104, paddingHorizontal: 15, paddingVertical: 11 }, secondary: { backgroundColor: theme === "dark" ? "#263733" : "#E8EEEC", borderColor: colors.border, borderWidth: 1 }, warm: { backgroundColor: theme === "dark" ? "#3A2C22" : "#FFF2E5", borderColor: colors.accent, borderWidth: 1 }, buttonText: { color: theme === "dark" ? colors.background : colors.white, fontWeight: "800" }, darkButtonText: { color: colors.text }, disabled: { opacity: .55 },
  dropdownWrap: { gap: 4 }, dropdown: { alignItems: "center", backgroundColor: theme === "dark" ? "#22332F" : colors.white, borderColor: colors.border, borderRadius: 11, borderWidth: 1, flexDirection: "row", justifyContent: "space-between", padding: 12 }, dropdownText: { color: colors.text, fontSize: 15, fontWeight: "700" }, dropdownMenu: { backgroundColor: theme === "dark" ? "#22332F" : colors.white, borderColor: colors.border, borderRadius: 11, borderWidth: 1, overflow: "hidden" }, dropdownItem: { paddingHorizontal: 12, paddingVertical: 11 }, dropdownItemSelected: { backgroundColor: colors.primarySoft },
  calendarDay: { alignItems: "center", height: 76, justifyContent: "center", overflow: "hidden", paddingHorizontal: 1, width: "100%" },
  calendarDaySelected: { backgroundColor: colors.primary, borderRadius: 10 },
  calendarRangeDay: { backgroundColor: theme === "dark" ? "#214B43" : "#D7EFEB" },
  calendarRangeStart: { backgroundColor: colors.primary, borderBottomLeftRadius: 18, borderTopLeftRadius: 18 },
  calendarRangeEnd: { backgroundColor: colors.primary, borderBottomRightRadius: 18, borderTopRightRadius: 18 },
  calendarDayNumber: { color: colors.text, fontSize: 15 },
  calendarDayDisabled: { color: theme === "dark" ? "#52645F" : "#C4CECB" },
  calendarDaySelectedText: { color: theme === "dark" ? colors.background : colors.white, fontWeight: "800" },
  calendarHolidayText: { color: colors.danger, fontWeight: "800" },
  calendarCount: { color: theme === "dark" ? colors.accent : "#111111", fontSize: 10, fontWeight: "900", lineHeight: 13 },
  calendarMetaPlaceholder: { height: 13 },
  calendarHolidayName: { color: colors.danger, fontSize: 9, fontWeight: "700", lineHeight: 12, maxWidth: "100%" },
  calendarHolidayPlaceholder: { height: 12 },
  calendarNotificationName: { color: IMPORTANT_DAY_COLOR, fontSize: 9, fontWeight: "800", lineHeight: 12, maxWidth: "100%" },
  photoDivider: { color: colors.textMuted, fontSize: 13, fontWeight: "700", textAlign: "center" },
  photoActions: { flexDirection: "row", flexWrap: "wrap", gap: 10, justifyContent: "center" },
  iconButton: { alignItems: "center", backgroundColor: colors.primary, borderRadius: 11, flexDirection: "row", gap: 7, justifyContent: "center", minWidth: 132, paddingHorizontal: 15, paddingVertical: 11 },
  dietImage: { alignSelf: "center", borderRadius: 14, height: 180, resizeMode: "cover", width: "100%" },
  reviewTitle: { color: colors.text, fontSize: 18, fontWeight: "900" },
  uncertainBox: { backgroundColor: theme === "dark" ? "#3A2C22" : "#FFF5E8", borderColor: colors.accent, borderRadius: 12, borderWidth: 1, gap: 5, padding: 12 },
  uncertainTitle: { color: colors.text, fontWeight: "900" },
  uncertainText: { color: colors.text, lineHeight: 20 },
  successText: { color: colors.primary, fontWeight: "800", textAlign: "center" },
  nutritionCard: { backgroundColor: theme === "dark" ? "#22332F" : colors.primarySoft, borderColor: colors.border, borderRadius: 14, borderWidth: 1, overflow: "hidden" },
  nutritionRow: { alignItems: "center", borderBottomColor: colors.border, borderBottomWidth: StyleSheet.hairlineWidth, flexDirection: "row", justifyContent: "space-between", paddingHorizontal: 14, paddingVertical: 12 },
  nutritionLabel: { color: colors.textMuted, fontWeight: "700" },
  nutritionValue: { color: colors.text, fontWeight: "900" },
  previewDescription: { backgroundColor: theme === "dark" ? "#22332F" : colors.white, borderColor: colors.border, borderRadius: 11, borderWidth: 1, color: colors.text, lineHeight: 21, padding: 12 },
  aiNotice: { color: colors.accent, fontSize: 13, fontWeight: "800", lineHeight: 20, textAlign: "center" },
});
