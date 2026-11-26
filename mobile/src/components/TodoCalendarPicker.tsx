import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Calendar, type DateData } from "react-native-calendars";
import { ActivityIndicator, Modal, StyleSheet } from "react-native";

import { AppPressable as Pressable } from "@/components/AppPressable";
import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";
import { todayIsoDate } from "@/components/DateRangeFilter";
import { useAppPreferences } from "@/context/AppPreferencesContext";
import { useAuth } from "@/context/AuthContext";
import { getCalendarMonth, type CalendarDay } from "@/services/analyticsApi";

// 待辦事項的行事曆選取元件（2026-11-26，見 docs/ADR/discuss/robinson.md）：點一天＝單日待辦
// （start=end），點第二天形成區間；沿用 DateRangeFilter.tsx 的 range-select 寫法，但刻意精簡
// （不做最小/最大天數限制）。
// 2026-11-26（同日修正）：Robin 反饋數字下方的國定假日名稱小字會讓日期擠成一團，拿掉；且
// 打開行事曆時會先看到「黑色→等資料載入完才變紅色」的閃爍，改成打開當下先讀取該月份國定假日
// 資料、讀完才顯示行事曆，避免分階段跳動。
type Props = {
  endDate: string;
  startDate: string;
  onChange: (range: { start: string; end: string }) => void;
};

export function TodoCalendarPicker({ endDate, startDate, onChange }: Props) {
  const { colors, theme } = useAppPreferences();
  const { authorizedRequest } = useAuth();
  const styles = createStyles(colors, theme);
  const [open, setOpen] = useState(false);
  const [selectionStarted, setSelectionStarted] = useState(false);
  const [calendarDays, setCalendarDays] = useState<Record<string, CalendarDay>>({});
  const [loadedMonths, setLoadedMonths] = useState<Record<string, boolean>>({});

  const loadMonth = useCallback(
    (month: string) => {
      const [year, monthIndex] = month.split("-").map(Number);
      void getCalendarMonth(authorizedRequest, year, monthIndex)
        .then((result) => {
          setCalendarDays((current) => ({ ...current, ...result.days }));
          setLoadedMonths((current) => ({ ...current, [month]: true }));
        })
        .catch(() => setLoadedMonths((current) => ({ ...current, [month]: true })));
    },
    [authorizedRequest],
  );

  useEffect(() => {
    if (!open) return;
    const month = (startDate || todayIsoDate()).slice(0, 7);
    if (!loadedMonths[month]) loadMonth(month);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const markedDates = useMemo(() => {
    const endpointTextColor = theme === "dark" ? colors.background : colors.white;
    if (!startDate) return {};
    if (!endDate) {
      return { [startDate]: { startingDay: true, endingDay: true, color: colors.primary, textColor: endpointTextColor } };
    }
    const marks: Record<string, { startingDay?: boolean; endingDay?: boolean; color: string; textColor: string }> = {};
    const cursor = new Date(`${startDate}T00:00:00`);
    const end = new Date(`${endDate}T00:00:00`);
    while (cursor <= end) {
      const year = cursor.getFullYear();
      const monthValue = String(cursor.getMonth() + 1).padStart(2, "0");
      const dayValue = String(cursor.getDate()).padStart(2, "0");
      const iso = `${year}-${monthValue}-${dayValue}`;
      marks[iso] = {
        startingDay: iso === startDate,
        endingDay: iso === endDate,
        color: iso === startDate || iso === endDate ? colors.primary : theme === "dark" ? "#28574F" : "#BCE1D8",
        textColor: iso === startDate || iso === endDate ? endpointTextColor : colors.text,
      };
      cursor.setDate(cursor.getDate() + 1);
    }
    return marks;
  }, [colors, endDate, startDate, theme]);

  const selectDay = (day: DateData) => {
    if (!selectionStarted) {
      onChange({ start: day.dateString, end: day.dateString });
      setSelectionStarted(true);
      return;
    }
    onChange(
      day.dateString < startDate
        ? { start: day.dateString, end: startDate }
        : { start: startDate, end: day.dateString },
    );
    setSelectionStarted(false);
  };

  return (
    <View style={styles.wrapper}>
      <Pressable
        onPress={() => { setSelectionStarted(false); setOpen(true); }}
        style={styles.selector}
      >
        <MaterialCommunityIcons color={colors.primary} name="calendar-range" size={22} />
        <View style={styles.selectorText}>
          <Text style={styles.label}>提醒日期</Text>
          <Text style={styles.value}>{startDate === endDate ? startDate : `${startDate} ～ ${endDate}`}</Text>
        </View>
        <MaterialCommunityIcons color={colors.textMuted} name="chevron-down" size={22} />
      </Pressable>
      <Modal animationType="fade" onRequestClose={() => setOpen(false)} transparent visible={open}>
        <View style={styles.modalRoot}>
          <Pressable onPress={() => setOpen(false)} style={styles.backdrop} />
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>選擇提醒日期</Text>
            <Text style={styles.modalHint}>點一天＝單日待辦，再點第二天可形成日期區間</Text>
            {loadedMonths[(startDate || todayIsoDate()).slice(0, 7)] ? (
              <Calendar
                current={startDate || todayIsoDate()}
                dayComponent={({ date, marking, state }) => {
                  if (!date) return null;
                  const isToday = date.dateString === todayIsoDate();
                  const calendarDay = calendarDays[date.dateString];
                  return (
                    <Pressable
                      onPress={() => selectDay(date)}
                      style={[
                        styles.rangeDay,
                        marking?.color ? { backgroundColor: marking.color } : null,
                        marking?.startingDay && styles.rangeStart,
                        marking?.endingDay && styles.rangeEnd,
                        isToday && !marking?.color && styles.todayDay,
                      ]}
                    >
                      <Text
                        style={[
                          styles.rangeDayText,
                          state === "disabled" && styles.disabledDayText,
                          marking?.textColor ? { color: marking.textColor } : null,
                          calendarDay?.is_holiday && !isToday && styles.holidayDayText,
                          isToday && !marking?.color && styles.todayDayText,
                        ]}
                      >
                        {date.day}
                      </Text>
                    </Pressable>
                  );
                }}
                markedDates={markedDates}
                markingType="period"
                onDayPress={selectDay}
                onMonthChange={(month) => loadMonth(month.dateString.slice(0, 7))}
                theme={{
                  arrowColor: colors.primary,
                  calendarBackground: colors.surface,
                  dayTextColor: colors.text,
                  monthTextColor: colors.text,
                  textSectionTitleColor: colors.textMuted,
                  textDisabledColor: theme === "dark" ? "#52645F" : "#C4CECB",
                  textMonthFontWeight: "800" as const,
                  todayTextColor: colors.danger,
                }}
              />
            ) : (
              <View style={styles.loadingBox}>
                <ActivityIndicator color={colors.primary} />
              </View>
            )}
            <View style={styles.actions}>
              <Pressable onPress={() => setOpen(false)} style={styles.applyButton}>
                <Text style={styles.applyText}>完成</Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const createStyles = (colors: ReturnType<typeof useAppPreferences>["colors"], theme: ReturnType<typeof useAppPreferences>["theme"]) => StyleSheet.create({
  wrapper: { gap: 7 },
  selector: { alignItems: "center", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 13, borderWidth: 1, flexDirection: "row", gap: 12, paddingHorizontal: 14, paddingVertical: 11 },
  selectorText: { flex: 1, gap: 3 },
  label: { color: colors.textMuted, fontSize: 11, fontWeight: "700" },
  value: { color: colors.text, fontSize: 14, fontWeight: "800" },
  modalRoot: { alignItems: "center", flex: 1, justifyContent: "center", padding: 18 },
  backdrop: { backgroundColor: "rgba(18, 35, 32, 0.48)", bottom: 0, left: 0, position: "absolute", right: 0, top: 0 },
  modalCard: { backgroundColor: colors.surface, borderRadius: 20, elevation: 10, gap: 8, maxWidth: 430, padding: 18, width: "100%" },
  modalTitle: { color: colors.text, fontSize: 19, fontWeight: "900" },
  modalHint: { color: colors.textMuted, fontSize: 12 },
  actions: { flexDirection: "row", gap: 10, justifyContent: "flex-end", marginTop: 8 },
  applyButton: { backgroundColor: colors.primary, borderRadius: 10, paddingHorizontal: 20, paddingVertical: 10 },
  applyText: { color: theme === "dark" ? colors.background : colors.white, fontWeight: "800" },
  loadingBox: { alignItems: "center", height: 260, justifyContent: "center" },
  rangeDay: { alignItems: "center", height: 64, justifyContent: "center", overflow: "hidden", width: "100%" },
  rangeDayText: { color: colors.text, fontSize: 16 },
  rangeStart: { borderBottomLeftRadius: 19, borderTopLeftRadius: 19 },
  rangeEnd: { borderBottomRightRadius: 19, borderTopRightRadius: 19 },
  todayDay: { backgroundColor: colors.danger, borderRadius: 19 },
  todayDayText: { color: colors.white, fontWeight: "900" },
  disabledDayText: { color: theme === "dark" ? "#52645F" : "#C4CECB" },
  calendarLabel: { color: colors.textMuted, fontSize: 9, fontWeight: "700", lineHeight: 12, maxWidth: "100%" },
  holidayLabel: { color: colors.danger },
  holidayDayText: { color: colors.danger, fontWeight: "800" },
});
