import { useCallback, useEffect, useMemo, useState } from "react";
import { Calendar, type DateData } from "react-native-calendars";
import { StyleSheet } from "react-native";

import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";
import { todayIsoDate } from "@/components/DateRangeFilter";
import { useAppPreferences } from "@/context/AppPreferencesContext";
import { useAuth } from "@/context/AuthContext";
import { getBirthdays, getCalendarMonth, getTodos, type Birthday, type CalendarDay, type TodoItem } from "@/services/analyticsApi";

// 首頁行事曆（2026-11-26，取代舊的「重要通知」卡片，見 docs/ADR/discuss/robinson.md）：
// 週休二日／國定假日數字亮紅色，平日黑色；數字下方用小字顯示當天的待辦事項／生日／國定假日
// 名稱；支援左右翻頁看上個月/下個月（沿用 react-native-calendars 內建的月份切換箭頭）。
// 待辦與生日清單資料量小，一次整包抓取後在前端依月份／日期篩選，不額外要求後端按月份篩選。
function monthKeyOf(iso: string): string {
  return iso.slice(0, 7);
}

function daysInRange(start: string, end: string): string[] {
  const result: string[] = [];
  const cursor = new Date(`${start}T00:00:00`);
  const last = new Date(`${end}T00:00:00`);
  while (cursor <= last) {
    const year = cursor.getFullYear();
    const month = String(cursor.getMonth() + 1).padStart(2, "0");
    const day = String(cursor.getDate()).padStart(2, "0");
    result.push(`${year}-${month}-${day}`);
    cursor.setDate(cursor.getDate() + 1);
  }
  return result;
}

export function HomeCalendar() {
  const { colors, theme } = useAppPreferences();
  const { authorizedRequest } = useAuth();
  const styles = createStyles(colors, theme);
  const [calendarDays, setCalendarDays] = useState<Record<string, CalendarDay>>({});
  const [todos, setTodos] = useState<TodoItem[]>([]);
  const [birthdays, setBirthdays] = useState<Birthday[]>([]);

  const loadMonth = useCallback(
    (month: string) => {
      const [year, monthIndex] = month.split("-").map(Number);
      void getCalendarMonth(authorizedRequest, year, monthIndex)
        .then((result) => setCalendarDays((current) => ({ ...current, ...result.days })))
        .catch(() => undefined);
    },
    [authorizedRequest],
  );

  useEffect(() => {
    loadMonth(monthKeyOf(todayIsoDate()));
    void getTodos(authorizedRequest).then((result) => setTodos(result.items)).catch(() => undefined);
    void getBirthdays(authorizedRequest).then((result) => setBirthdays(result.items)).catch(() => undefined);
  }, [authorizedRequest, loadMonth]);

  const todosByDate = useMemo(() => {
    const map: Record<string, string[]> = {};
    for (const item of todos) {
      for (const iso of daysInRange(item.remind_start_date, item.remind_end_date)) {
        (map[iso] ??= []).push(item.content);
      }
    }
    return map;
  }, [todos]);

  const birthdaysByMonthDay = useMemo(() => {
    const map: Record<string, string[]> = {};
    for (const item of birthdays) {
      const key = `${item.birth_month}-${item.birth_day}`;
      (map[key] ??= []).push(item.name);
    }
    return map;
  }, [birthdays]);

  return (
    <View style={styles.wrapper}>
      <Calendar
        current={todayIsoDate()}
        dayComponent={({ date, state }) => {
          if (!date) return null;
          const calendarDay = calendarDays[date.dateString];
          const isWeekendOrHoliday = Boolean(calendarDay?.is_holiday);
          const todoTexts = todosByDate[date.dateString] ?? [];
          const birthdayTexts = birthdaysByMonthDay[`${date.month}-${date.day}`] ?? [];
          const notes: string[] = [];
          if (calendarDay?.name) notes.push(calendarDay.name);
          if (birthdayTexts.length) notes.push(`🎂${birthdayTexts.join("、")}`);
          if (todoTexts.length) notes.push(todoTexts.length > 1 ? `${todoTexts[0]} 等 ${todoTexts.length} 筆` : todoTexts[0]);
          return (
            <View style={styles.day}>
              <Text style={[styles.dayText, isWeekendOrHoliday && styles.holidayDayText, state === "disabled" && styles.disabledDayText]}>
                {date.day}
              </Text>
              {notes.map((note, index) => (
                <Text key={`${date.dateString}-note-${index}`} numberOfLines={1} style={styles.noteText}>
                  {note}
                </Text>
              ))}
            </View>
          );
        }}
        onMonthChange={(month) => loadMonth(month.dateString.slice(0, 7))}
        theme={{
          arrowColor: colors.primary,
          calendarBackground: colors.surface,
          dayTextColor: colors.text,
          monthTextColor: colors.text,
          textSectionTitleColor: colors.textMuted,
          textDisabledColor: theme === "dark" ? "#52645F" : "#C4CECB",
          textMonthFontWeight: "800" as const,
        }}
      />
    </View>
  );
}

const createStyles = (colors: ReturnType<typeof useAppPreferences>["colors"], theme: ReturnType<typeof useAppPreferences>["theme"]) => StyleSheet.create({
  wrapper: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 18, borderWidth: 1, overflow: "hidden", padding: 6 },
  day: { alignItems: "center", height: 60, justifyContent: "flex-start", overflow: "hidden", paddingTop: 4, width: "100%" },
  dayText: { color: colors.text, fontSize: 15, fontWeight: "700" },
  holidayDayText: { color: colors.danger, fontWeight: "900" },
  disabledDayText: { color: theme === "dark" ? "#52645F" : "#C4CECB" },
  noteText: { color: colors.textMuted, fontSize: 9, fontWeight: "600", lineHeight: 11, maxWidth: "100%" },
});
