import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";
import { useEffect, useMemo, useState } from "react";
import { Calendar, LocaleConfig, type DateData } from "react-native-calendars";
import { Modal, StyleSheet } from "react-native";

import { AppPressable as Pressable } from "@/components/AppPressable";
import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";
import { useAppPreferences } from "@/context/AppPreferencesContext";
import type { DateRange, TodoAnalytics } from "@/services/analyticsApi";
import { calendarImportantDaySummary, IMPORTANT_DAY_COLOR } from "@/utils/calendarLabels";

LocaleConfig.locales["zh-tw"] = {
  monthNames: ["一月", "二月", "三月", "四月", "五月", "六月", "七月", "八月", "九月", "十月", "十一月", "十二月"],
  monthNamesShort: ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"],
  dayNames: ["星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六"],
  dayNamesShort: ["日", "一", "二", "三", "四", "五", "六"],
  today: "今天",
};
LocaleConfig.defaultLocale = "zh-tw";

function toIsoDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function todayIsoDate(): string {
  return toIsoDate(new Date());
}

export function defaultDateRange(): DateRange {
  const end = new Date();
  const start = new Date(end);
  start.setDate(start.getDate() - 6);
  return { start: toIsoDate(start), end: toIsoDate(end) };
}

export function validateDateRange(
  range: DateRange,
  { allowFuture = false, maxDays = 30, minDays = 7 }: Pick<RangeProps, "allowFuture" | "maxDays" | "minDays"> = {},
): string | null {
  if (!range.start || !range.end) {
    return "請再選擇一個日期，才能形成日期區間";
  }
  const start = new Date(`${range.start}T00:00:00`);
  const end = new Date(`${range.end}T00:00:00`);
  if (start > end) return "開始日期不可晚於結束日期";
  const days = Math.round((end.getTime() - start.getTime()) / 86_400_000) + 1;
  if (days < minDays || days > maxDays) return `日期區間必須介於 ${minDays} 到 ${maxDays} 天`;
  if (!allowFuture && range.end > todayIsoDate()) return "不可查詢未來日期";
  return null;
}

type ThemeColors = ReturnType<typeof useAppPreferences>["colors"];
type AppTheme = ReturnType<typeof useAppPreferences>["theme"];

function rangeMarks(range: DateRange, colors: ThemeColors, theme: AppTheme) {
  const endpointTextColor = theme === "dark" ? colors.background : colors.white;
  if (!range.start) return {};
  if (!range.end) {
    return { [range.start]: { startingDay: true, endingDay: true, color: colors.primary, textColor: endpointTextColor } };
  }
  const marks: Record<string, { startingDay?: boolean; endingDay?: boolean; color: string; textColor: string }> = {};
  const cursor = new Date(`${range.start}T00:00:00`);
  const end = new Date(`${range.end}T00:00:00`);
  while (cursor <= end) {
    const date = toIsoDate(cursor);
    marks[date] = {
      startingDay: date === range.start,
      endingDay: date === range.end,
      color: date === range.start || date === range.end ? colors.primary : theme === "dark" ? "#28574F" : "#BCE1D8",
      textColor: date === range.start || date === range.end ? endpointTextColor : colors.text,
    };
    cursor.setDate(cursor.getDate() + 1);
  }
  return marks;
}

const createCalendarTheme = (colors: ThemeColors, theme: AppTheme) => ({
  arrowColor: colors.primary,
  calendarBackground: colors.surface,
  dayTextColor: colors.text,
  monthTextColor: colors.text,
  textSectionTitleColor: colors.textMuted,
  textDisabledColor: theme === "dark" ? "#52645F" : "#C4CECB",
  textMonthFontWeight: "800" as const,
  todayTextColor: colors.danger,
});

type RangeProps = {
  allowFuture?: boolean;
  calendarCounts?: TodoAnalytics["calendar_counts"];
  calendarDays?: TodoAnalytics["calendar_days"];
  holidayOnly?: boolean;
  hint?: string;
  maxDays?: number;
  minDays?: number;
  range: DateRange;
  onCalendarMonthChange?: (month: string) => void;
  onApply: (range: DateRange) => void;
};

export function DateRangeFilter({ allowFuture = false, calendarCounts = {}, calendarDays = {}, holidayOnly = false, hint = "可查任意歷史日期，每次區間最少 7 天、最多 30 天", maxDays = 30, minDays = 7, onCalendarMonthChange, range, onApply }: RangeProps) {
  const { colors, theme } = useAppPreferences();
  const styles = createStyles(colors, theme);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<DateRange>(range);
  const [selectionStarted, setSelectionStarted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setDraft(range), [range]);
  const markedDates = useMemo(() => rangeMarks(draft, colors, theme), [colors, draft, theme]);

  const selectDay = (day: DateData) => {
    setError(null);
    if (!selectionStarted) {
      setDraft({ start: day.dateString, end: minDays === 1 ? day.dateString : "" });
      setSelectionStarted(true);
      return;
    }
    setDraft(
      day.dateString < draft.start
        ? { start: day.dateString, end: draft.start }
        : { start: draft.start, end: day.dateString },
    );
    setSelectionStarted(false);
  };

  const apply = () => {
    const validationError = validateDateRange(draft, { allowFuture, maxDays, minDays });
    setError(validationError);
    if (!validationError) {
      onApply(draft);
      setOpen(false);
      setSelectionStarted(false);
    }
  };

  return (
    <View style={styles.wrapper}>
      <Pressable
        onPress={() => { setDraft(range); setError(null); setSelectionStarted(false); setOpen(true); }}
        style={styles.selector}
      >
        <MaterialCommunityIcons color={colors.primary} name="calendar-range" size={22} />
        <View style={styles.selectorText}><Text style={styles.label}>日期區間</Text><Text style={styles.value}>{range.start} ～ {range.end}</Text></View>
        <MaterialCommunityIcons color={colors.textMuted} name="chevron-down" size={22} />
      </Pressable>
      <Text style={styles.hint}>{hint}</Text>
      <Modal animationType="fade" onRequestClose={() => setOpen(false)} transparent visible={open}>
        <View style={styles.modalRoot}>
          <Pressable onPress={() => setOpen(false)} style={styles.backdrop} />
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>選擇日期區間</Text>
            <Text style={styles.modalHint}>依序點選開始與結束日期</Text>
            <Calendar
              current={draft.start || range.start}
              dayComponent={({ date, marking, state }) => {
                if (!date) return null;
                const isToday = date.dateString === todayIsoDate();
                const count = calendarCounts[date.dateString] ?? 0;
                const calendarDay = calendarDays[date.dateString];
                return (
                  <Pressable
                    onPress={() => selectDay(date)}
                    style={[
                      styles.rangeDay,
                      marking?.color ? { backgroundColor: marking.color } : null,
                      marking?.startingDay && styles.rangeStart,
                      marking?.endingDay && styles.rangeEnd,
                      isToday && styles.todayDay,
                    ]}
                  >
                    <Text
                      style={[
                        styles.rangeDayText,
                        state === "disabled" && styles.disabledDayText,
                        marking?.textColor ? { color: marking.textColor } : null,
                        calendarDay?.is_holiday && !isToday && styles.holidayDayText,
                        isToday && styles.todayDayText,
                      ]}
                    >
                      {date.day}
                    </Text>
                    {!holidayOnly && count > 0 ? <Text style={styles.todoCount}>{count}件</Text> : <View style={styles.todoCountPlaceholder} />}
                    {calendarDay?.name ? <Text numberOfLines={1} style={[styles.calendarLabel, calendarDay.is_holiday && styles.holidayLabel]}>{calendarDay.name}</Text> : null}
                    {!holidayOnly && calendarImportantDaySummary(calendarDay) ? <Text numberOfLines={1} style={styles.notificationLabel}>{calendarImportantDaySummary(calendarDay)}</Text> : null}
                  </Pressable>
                );
              }}
              markedDates={markedDates}
              markingType="period"
              maxDate={allowFuture ? undefined : todayIsoDate()}
              onDayPress={selectDay}
              onMonthChange={(month) => onCalendarMonthChange?.(month.dateString.slice(0, 7))}
              theme={createCalendarTheme(colors, theme)}
            />
            {error ? <Text style={styles.error}>{error}</Text> : null}
            <View style={styles.actions}>
              <Pressable onPress={() => setOpen(false)} style={styles.cancelButton}><Text style={styles.cancelText}>取消</Text></Pressable>
              <Pressable onPress={apply} style={styles.applyButton}><Text style={styles.applyText}>套用</Text></Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

type SingleProps = {
  calendarDays?: TodoAnalytics["calendar_days"];
  date: string;
  onCalendarMonthChange?: (month: string) => void;
  onApply: (date: string) => void;
};

export function SingleDateFilter({ calendarDays = {}, date, onCalendarMonthChange, onApply }: SingleProps) {
  const { colors, theme } = useAppPreferences();
  const styles = createStyles(colors, theme);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(date);
  return (
    <View style={styles.wrapper}>
      <Pressable onPress={() => { setDraft(date); setOpen(true); }} style={styles.selector}>
        <MaterialCommunityIcons color={colors.primary} name="calendar-today" size={22} />
        <View style={styles.selectorText}><Text style={styles.label}>技術分享日期</Text><Text style={styles.value}>{date}</Text></View>
        <MaterialCommunityIcons color={colors.textMuted} name="chevron-down" size={22} />
      </Pressable>
      <Text style={styles.hint}>技術分享資料量較多，每次只查看一天</Text>
      <Modal animationType="fade" onRequestClose={() => setOpen(false)} transparent visible={open}>
        <View style={styles.modalRoot}>
          <Pressable onPress={() => setOpen(false)} style={styles.backdrop} />
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>選擇日期</Text>
            <Calendar
              current={draft}
              dayComponent={({ date: calendarDate, marking, state }) => {
                if (!calendarDate) return null;
                const calendarDay = calendarDays[calendarDate.dateString];
                const isToday = calendarDate.dateString === todayIsoDate();
                return <Pressable onPress={() => setDraft(calendarDate.dateString)} style={[styles.rangeDay, marking?.selected && styles.singleSelectedDay, isToday && styles.todayDay]}>
                  <Text style={[styles.rangeDayText, state === "disabled" && styles.disabledDayText, marking?.selected && styles.singleSelectedDayText, calendarDay?.is_holiday && !isToday && styles.holidayDayText, isToday && styles.todayDayText]}>{calendarDate.day}</Text>
                  <View style={styles.todoCountPlaceholder} />
                  {calendarDay?.name ? <Text numberOfLines={1} style={[styles.calendarLabel, calendarDay.is_holiday && styles.holidayLabel]}>{calendarDay.name}</Text> : null}
                </Pressable>;
              }}
              markedDates={{ [draft]: { selected: true, selectedColor: colors.primary, selectedTextColor: theme === "dark" ? colors.background : colors.white } }}
              maxDate={todayIsoDate()}
              onDayPress={(day) => setDraft(day.dateString)}
              onMonthChange={(month) => onCalendarMonthChange?.(month.dateString.slice(0, 7))}
              theme={createCalendarTheme(colors, theme)}
            />
            <View style={styles.actions}>
              <Pressable onPress={() => setOpen(false)} style={styles.cancelButton}><Text style={styles.cancelText}>取消</Text></Pressable>
              <Pressable onPress={() => { onApply(draft); setOpen(false); }} style={styles.applyButton}><Text style={styles.applyText}>套用</Text></Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const createStyles = (colors: ThemeColors, theme: AppTheme) => StyleSheet.create({
  wrapper: { gap: 7 },
  selector: { alignItems: "center", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 13, borderWidth: 1, flexDirection: "row", gap: 12, paddingHorizontal: 14, paddingVertical: 11 },
  selectorText: { flex: 1, gap: 3 },
  label: { color: colors.textMuted, fontSize: 11, fontWeight: "700" },
  value: { color: colors.text, fontSize: 14, fontWeight: "800" },
  hint: { color: colors.textMuted, fontSize: 11 },
  modalRoot: { alignItems: "center", flex: 1, justifyContent: "center", padding: 18 },
  backdrop: { backgroundColor: "rgba(18, 35, 32, 0.48)", bottom: 0, left: 0, position: "absolute", right: 0, top: 0 },
  modalCard: { backgroundColor: colors.surface, borderRadius: 20, elevation: 10, gap: 8, maxWidth: 430, padding: 18, width: "100%" },
  modalTitle: { color: colors.text, fontSize: 19, fontWeight: "900" },
  modalHint: { color: colors.textMuted, fontSize: 12 },
  error: { color: colors.danger, fontSize: 12, fontWeight: "700" },
  actions: { flexDirection: "row", gap: 10, justifyContent: "flex-end", marginTop: 8 },
  cancelButton: { borderColor: colors.border, borderRadius: 10, borderWidth: 1, paddingHorizontal: 18, paddingVertical: 10 },
  cancelText: { color: colors.textMuted, fontWeight: "800" },
  applyButton: { backgroundColor: colors.primary, borderRadius: 10, paddingHorizontal: 20, paddingVertical: 10 },
  applyText: { color: colors.white, fontWeight: "800" },
  rangeDay: { alignItems: "center", height: 76, justifyContent: "center", overflow: "hidden", width: "100%" },
  rangeDayText: { color: colors.text, fontSize: 16 },
  rangeStart: { borderBottomLeftRadius: 19, borderTopLeftRadius: 19 },
  rangeEnd: { borderBottomRightRadius: 19, borderTopRightRadius: 19 },
  singleSelectedDay: { backgroundColor: colors.primary, borderRadius: 19 },
  singleSelectedDayText: { color: theme === "dark" ? colors.background : colors.white, fontWeight: "800" },
  todayDay: { backgroundColor: colors.danger, borderRadius: 19 },
  todayDayText: { color: colors.white, fontWeight: "900" },
  disabledDayText: { color: theme === "dark" ? "#52645F" : "#C4CECB" },
  todoCount: { color: theme === "dark" ? colors.accent : "#111111", fontSize: 10, fontWeight: "900", lineHeight: 13 },
  todoCountPlaceholder: { height: 13 },
  calendarLabel: { color: colors.textMuted, fontSize: 9, fontWeight: "700", lineHeight: 12, maxWidth: "100%" },
  holidayLabel: { color: colors.danger },
  holidayDayText: { color: colors.danger, fontWeight: "800" },
  notificationLabel: { color: IMPORTANT_DAY_COLOR, fontSize: 9, fontWeight: "800", lineHeight: 12, maxWidth: "100%" },
});
