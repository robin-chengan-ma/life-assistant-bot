export const IMPORTANT_DAY_COLOR = "#3B82F6";

type CalendarLabelDay = {
  name?: string | null;
  important_notifications?: string[];
};

function normalizedLabels(value: string | null | undefined): Set<string> {
  return new Set(
    (value ?? "")
      .split("／")
      .map((label) => label.trim())
      .filter(Boolean),
  );
}

export function uniqueImportantDayLabels(day: CalendarLabelDay | null | undefined): string[] {
  const holidayLabels = normalizedLabels(day?.name);
  return [...new Set(day?.important_notifications ?? [])]
    .map((label) => label.trim())
    .filter((label) => label && !holidayLabels.has(label));
}

export function calendarImportantDaySummary(day: CalendarLabelDay | null | undefined): string | null {
  const labels = uniqueImportantDayLabels(day);
  if (labels.length === 0) return null;
  if (labels.length === 1) return labels[0];
  return `${labels[0]} +${labels.length - 1}`;
}
