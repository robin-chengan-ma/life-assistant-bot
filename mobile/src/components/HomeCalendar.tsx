import { useCallback, useEffect, useMemo, useState } from "react";
import { Calendar, type DateData } from "react-native-calendars";
import { ActivityIndicator, StyleSheet } from "react-native";

import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";
import { todayIsoDate } from "@/components/DateRangeFilter";
import { useAppPreferences } from "@/context/AppPreferencesContext";
import { useAuth } from "@/context/AuthContext";
import { getBirthdays, getCalendarMonth, getTodos, type Birthday, type CalendarDay, type TodoItem } from "@/services/analyticsApi";

// 首頁行事曆（2026-11-26，取代舊的「重要通知」卡片，見 docs/ADR/discuss/robinson.md）：
// 週休二日／國定假日數字亮紅色，平日黑色；支援左右翻頁看上個月/下個月（沿用
// react-native-calendars 內建的月份切換箭頭）。
// 2026-11-26（同日修正）：Robin 反饋數字下方的小字注記太擠看不清楚，且月份切換時會先看到
// 「黑色→等資料載入完才變紅色」的閃爍，不喜歡這種體感。改為：①數字下方完全不顯示任何小字，
// 待辦／生日／國定假日的詳細內容改到行事曆下方獨立的「未來一週注意事項」區塊列出；②切換月份
// 時先隱藏行事曆、顯示讀取中，等該月份的國定假日資料全部到齊才一次顯示，避免色彩分階段跳動。
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

function addDays(iso: string, amount: number): string {
  const cursor = new Date(`${iso}T00:00:00`);
  cursor.setDate(cursor.getDate() + amount);
  const year = cursor.getFullYear();
  const month = String(cursor.getMonth() + 1).padStart(2, "0");
  const day = String(cursor.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatMonthDay(iso: string): string {
  const [, month, day] = iso.split("-");
  return `${Number(month)}/${Number(day)}`;
}

export function HomeCalendar() {
  const { colors, theme } = useAppPreferences();
  const { authorizedRequest } = useAuth();
  const styles = createStyles(colors, theme);
  const [calendarDays, setCalendarDays] = useState<Record<string, CalendarDay>>({});
  const [todos, setTodos] = useState<TodoItem[]>([]);
  const [birthdays, setBirthdays] = useState<Birthday[]>([]);
  const [visibleMonth, setVisibleMonth] = useState(monthKeyOf(todayIsoDate()));
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
    loadMonth(visibleMonth);
    void getTodos(authorizedRequest).then((result) => setTodos(result.items)).catch(() => undefined);
    void getBirthdays(authorizedRequest).then((result) => setBirthdays(result.items)).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authorizedRequest]);

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

  const weeklyNotices = useMemo(() => {
    const today = todayIsoDate();
    const notices: Array<{ date: string; label: string; lines: string[] }> = [];
    for (let offset = 0; offset < 7; offset += 1) {
      const iso = addDays(today, offset);
      const [, month, day] = iso.split("-").map(Number);
      const lines: string[] = [];
      const calendarDay = calendarDays[iso];
      if (calendarDay?.name) lines.push(`🎉 ${calendarDay.name}`);
      const birthdayNames = birthdaysByMonthDay[`${month}-${day}`] ?? [];
      if (birthdayNames.length) lines.push(`🎂 ${birthdayNames.join("、")}生日`);
      for (const content of todosByDate[iso] ?? []) lines.push(`📌 ${content}`);
      if (!lines.length) continue;
      notices.push({ date: iso, label: offset === 0 ? `${formatMonthDay(iso)}（今天）` : formatMonthDay(iso), lines });
    }
    return notices;
  }, [calendarDays, birthdaysByMonthDay, todosByDate]);

  const monthReady = Boolean(loadedMonths[visibleMonth]);

  return (
    <View style={styles.wrapper}>
      {monthReady ? (
        <Calendar
          current={`${visibleMonth}-01`}
          dayComponent={({ date, state }) => {
            if (!date) return null;
            const calendarDay = calendarDays[date.dateString];
            const isWeekendOrHoliday = Boolean(calendarDay?.is_holiday);
            return (
              <View style={styles.day}>
                <Text style={[styles.dayText, isWeekendOrHoliday && styles.holidayDayText, state === "disabled" && styles.disabledDayText]}>
                  {date.day}
                </Text>
              </View>
            );
          }}
          onMonthChange={(month: DateData) => {
            const key = month.dateString.slice(0, 7);
            setVisibleMonth(key);
            if (!loadedMonths[key]) loadMonth(key);
          }}
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
      ) : (
        <View style={styles.loadingBox}>
          <ActivityIndicator color={colors.primary} />
        </View>
      )}
      <View style={styles.noticeBlock}>
        <Text style={styles.noticeTitle}>未來一週注意事項</Text>
        {weeklyNotices.length ? (
          weeklyNotices.map((notice) => (
            <View key={notice.date} style={styles.noticeRow}>
              <Text style={styles.noticeDate}>{notice.label}</Text>
              <View style={styles.noticeLines}>
                {notice.lines.map((line, index) => (
                  <Text key={`${notice.date}-${index}`} style={styles.noticeLine}>{line}</Text>
                ))}
              </View>
            </View>
          ))
        ) : (
          <Text style={styles.noticeEmpty}>未來一週目前沒有待辦、生日或國定假日</Text>
        )}
      </View>
    </View>
  );
}

const createStyles = (colors: ReturnType<typeof useAppPreferences>["colors"], theme: ReturnType<typeof useAppPreferences>["theme"]) => StyleSheet.create({
  wrapper: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 18, borderWidth: 1, overflow: "hidden", padding: 6 },
  loadingBox: { alignItems: "center", height: 320, justifyContent: "center" },
  day: { alignItems: "center", height: 40, justifyContent: "flex-start", overflow: "hidden", paddingTop: 4, width: "100%" },
  dayText: { color: colors.text, fontSize: 15, fontWeight: "700" },
  holidayDayText: { color: colors.danger, fontWeight: "900" },
  disabledDayText: { color: theme === "dark" ? "#52645F" : "#C4CECB" },
  noticeBlock: { borderColor: colors.border, borderTopWidth: 1, gap: 8, marginTop: 6, padding: 12 },
  noticeTitle: { color: colors.text, fontSize: 13, fontWeight: "900" },
  noticeRow: { flexDirection: "row", gap: 10 },
  noticeDate: { color: colors.primary, fontSize: 12, fontWeight: "800", width: 70 },
  noticeLines: { flex: 1, gap: 2 },
  noticeLine: { color: colors.textMuted, fontSize: 12, lineHeight: 17 },
  noticeEmpty: { color: colors.textMuted, fontSize: 12 },
});
