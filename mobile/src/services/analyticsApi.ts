import type { AppUser } from "@/services/authApi";

export type AnalyticsModule =
  | "todos"
  | "body"
  | "finance"
  | "mood"
  | "jobs"
  | "exams"
  | "skills"
  | "complaints";

export type NavigationItem = {
  label: string;
  color: string;
  is_enabled: boolean;
};

export type NavigationMap = Partial<Record<AnalyticsModule, NavigationItem>>;

export type DashboardResponse = {
  date: string;
  navigation: NavigationMap;
  notifications: string[];
  important_days: string[];
  summary: {
    todo_count?: number;
    expense_today?: number;
    expense_count?: number;
    income_today?: number;
    income_count?: number;
    fat_g?: number;
    protein_g?: number;
    carbs_g?: number;
    diet_calories?: number;
    diet_count?: number;
    water_ml?: number;
    exercise_calories?: number;
    exercise_count?: number;
    activities?: string | null;
    latest_weight?: number | null;
    weight_count?: number;
    latest_mood_category?: string | null;
    mood_count?: number;
  };
};

export type DateRange = { start: string; end: string };
export type AuthRequest = <T>(path: string, options?: RequestInit) => Promise<T>;

export type ImportantDay = {
  id: number;
  owner_user_id: number;
  title: string;
  recurrence_type: "fixed_annual" | "flexible_annual" | "one_time";
  event_date: string | null;
  event_end_date: string | null;
  event_month: number | null;
  event_day: number | null;
  event_end_month: number | null;
  event_end_day: number | null;
  event_time: string | null;
  current_year_date: string | null;
  current_year_end_date: string | null;
  current_year: number;
  next_occurrence: string | null;
  is_all_day: boolean;
  reminder_days_before: number;
  notes: string | null;
  audience_mode: "self" | "specific" | "all";
  recipient_ids: number[];
  show_on_todo_calendar: boolean;
  is_active: boolean;
  can_edit: boolean;
};

export type ImportantDayUser = { id: number; role: string; user_id: string };

export type FinanceAnalytics = {
  has_any_data: boolean;
  daily: Array<{ date: string; expense: number; income: number }>;
  expense_categories: Array<{ label: string; value: number }>;
  expense_total: number;
  income_total: number;
  records: Array<RecordItem>;
};

export type RecordKind = "todo" | "finance" | "diet" | "exercise" | "weight" | "mood";
export type RecordItem = Record<string, string | number | boolean | null> & { id: number; can_edit: boolean };
export type DietNutrition = {
  estimated_calories: number | null;
  protein_g: number | null;
  carbs_g: number | null;
  fat_g: number | null;
};

export type BodyAnalytics = {
  has_any_data: boolean;
  weight: Array<{ date: string; weight: number; waist: number | null; bmi: number | null }>;
  diet: Array<{
    date: string;
    water_ml: number;
    ai_count: number;
    manual_count: number;
    ai_fat_g: number;
    manual_fat_g: number;
    total_fat_g: number;
    ai_protein_g: number;
    manual_protein_g: number;
    total_protein_g: number;
    ai_carbs_g: number;
    manual_carbs_g: number;
    total_carbs_g: number;
    ai_calories: number;
    manual_calories: number;
    total_calories: number;
  }>;
  exercise: Array<{
    date: string;
    ai_count: number;
    manual_count: number;
    ai_calories: number;
    manual_calories: number;
    total_calories: number;
    minutes: number;
  }>;
  goals: Array<{
    goal_type: string;
    target_description: string;
    target_value: number | null;
    baseline_value: number | null;
    target_date: string | null;
  }>;
  body_defaults: { height_cm: number | null; weight_kg: number | null; waist_cm: number | null };
  latest_body_record: RecordItem | null;
  weight_records: Array<RecordItem>;
  diet_records: Array<RecordItem>;
  exercise_records: Array<RecordItem>;
};

export type TodoAnalytics = {
  has_any_data: boolean;
  calendar_counts: Record<string, number>;
  calendar_days: Record<string, {
    name: string | null;
    is_holiday: boolean;
    holiday_category: string | null;
    description: string | null;
    important_notifications?: string[];
  }>;
  items: Array<{
    id: number;
    content: string;
    due_at: string;
    start_at: string | null;
    status: string;
    created_at: string;
    can_edit: boolean;
  }>;
};

export type MoodAnalytics = {
  has_any_data: boolean;
  items: Array<{
    id: number;
    date: string;
    mood_category: string;
    content: string;
    achievement_note: string | null;
    created_at: string;
    can_edit: boolean;
  }>;
};

export type JobsAnalytics = {
  has_any_data: boolean;
  funnel: Record<string, number>;
  score_distribution: Record<string, number>;
  recommendations: Array<Record<string, string | number | null>>;
  timeline: Array<Record<string, string | number | null>>;
};

export type ExamsAnalytics = {
  has_any_data: boolean;
  goals: Array<Record<string, string | number | null>>;
  official_scores: Array<Record<string, string | number | null>>;
  practice: Array<Record<string, string | number | null>>;
};

export type SkillsAnalytics = {
  has_any_data: boolean;
  digests: Array<{ digest_date: string; source: string | null; summary_text: string | null }>;
  videos: Array<{
    pushed_on: string;
    topic: string | null;
    title: string | null;
    recommend_reason: string | null;
  }>;
};

export type ComplaintsAnalytics = {
  has_any_data: boolean;
  user_feedback: Array<{
    id: number;
    content: string;
    created_at: string;
    role: string;
  }>;
  system_errors: Array<{
    id: number;
    occurred_at: string;
    severity: string;
    triggering_feature: string | null;
    error_summary: string;
    drive_log_url: string | null;
    resolution: string | null;
  }>;
};

export type AnalyticsResponseMap = {
  todos: TodoAnalytics;
  body: BodyAnalytics;
  finance: FinanceAnalytics;
  mood: MoodAnalytics;
  jobs: JobsAnalytics;
  exams: ExamsAnalytics;
  skills: SkillsAnalytics;
  complaints: ComplaintsAnalytics;
};

export function getDashboard(request: AuthRequest): Promise<DashboardResponse> {
  return request<DashboardResponse>("/api/app/dashboard");
}

export function getAnalytics<M extends AnalyticsModule>(
  request: AuthRequest,
  module: M,
  range: DateRange,
  options?: { calendarMonth?: string },
): Promise<AnalyticsResponseMap[M]> {
  const queryParams = new URLSearchParams();
  if (module === "skills") {
    queryParams.set("date", range.start);
  } else {
    queryParams.set("start", range.start);
    queryParams.set("end", range.end);
  }
  if (module === "todos" && options?.calendarMonth) {
    queryParams.set("calendar_month", options.calendarMonth);
  }
  const query = queryParams.toString();
  return request<AnalyticsResponseMap[M]>(`/api/app/analytics/${module}?${query}`);
}

export function updateErrorResolution(
  request: AuthRequest,
  reportId: number,
  resolution: string,
): Promise<{ message: string }> {
  return request<{ message: string }>(`/api/app/system-errors/${reportId}/resolution`, {
    method: "PATCH",
    body: JSON.stringify({ resolution }),
  });
}

export function createWeightLog(
  request: AuthRequest,
  weightKg: number,
): Promise<{ id: number; message: string; weight_kg: number }> {
  return request<{ id: number; message: string; weight_kg: number }>("/api/app/body/weight-logs", {
    method: "POST",
    body: JSON.stringify({ weight_kg: weightKg }),
  });
}

export function createRecord(
  request: AuthRequest,
  kind: RecordKind,
  payload: Record<string, unknown>,
): Promise<{ id: number; message: string }> {
  return request(`/api/app/records/${kind}`, { method: "POST", body: JSON.stringify(payload) });
}

export function updateRecord(
  request: AuthRequest,
  kind: RecordKind,
  id: number,
  payload: Record<string, unknown>,
): Promise<{ id: number; message: string }> {
  return request(`/api/app/records/${kind}/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function deleteRecord(request: AuthRequest, kind: RecordKind, id: number): Promise<{ message: string }> {
  return request(`/api/app/records/${kind}/${id}`, { method: "DELETE" });
}

export function recognizeDietPhoto(
  request: AuthRequest,
  imageBase64: string,
  mimeType: string,
): Promise<{ description: string; uncertain_items: string[] }> {
  return request("/api/app/diet/recognize-photo", {
    method: "POST",
    body: JSON.stringify({ image_base64: imageBase64, mime_type: mimeType }),
  });
}

export function calculateDietNutrition(
  request: AuthRequest,
  payload: { confirmed_description: string; existing_description?: string; mode: "add" | "replace" },
): Promise<{ description: string; nutrition: DietNutrition }> {
  return request("/api/app/diet/calculate-nutrition", { method: "POST", body: JSON.stringify(payload) });
}

export function getImportantDays(request: AuthRequest): Promise<{ items: ImportantDay[]; users: ImportantDayUser[] }> {
  return request("/api/app/important-days");
}

export function createImportantDay(request: AuthRequest, payload: Record<string, unknown>): Promise<{ id: number; message: string }> {
  return request("/api/app/important-days", { method: "POST", body: JSON.stringify(payload) });
}

export function updateImportantDay(request: AuthRequest, id: number, payload: Record<string, unknown>): Promise<{ id: number; message: string }> {
  return request(`/api/app/important-days/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function deleteImportantDay(request: AuthRequest, id: number): Promise<{ message: string }> {
  return request(`/api/app/important-days/${id}`, { method: "DELETE" });
}

export function canAccessModule(user: AppUser, module: AnalyticsModule): boolean {
  return !["jobs", "exams", "skills", "complaints"].includes(module) || user.is_owner;
}
