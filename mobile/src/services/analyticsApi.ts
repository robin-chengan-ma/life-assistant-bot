export type AnalyticsModule = "body" | "finance";

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
  };
};

export type DateRange = { start: string; end: string };
export type AuthRequest = <T>(path: string, options?: RequestInit) => Promise<T>;

// 待辦事項：純粹的一次性提醒，只有日期區間與文字內容，沒有狀態／完成概念。
// 2026-11-26：remind_date（單一日期）改成 remind_start_date／remind_end_date（可為日期區間）。
// 2026-11-26（同日再追加，見 docs/ADR/discuss/robinson.md）：新增 remind_offsets（提前提醒天數
// 複選，邏輯跟生日設定一樣，但待辦一律僅推給自己，沒有推播對象選擇）。
// 2026-11-28（同日再追加）：新增 recurrence_type（once／monthly）與 recurrence_day（1~31，只有
// monthly 有意義），支援「每月固定一天」常態性待辦；monthly 類型時 remind_start_date／
// remind_end_date 一律是 null。
export type TodoRecurrenceType = "once" | "monthly";

export type TodoItem = {
  id: number;
  owner_user_id: number;
  content: string;
  recurrence_type: TodoRecurrenceType;
  recurrence_day: number | null;
  remind_start_date: string | null;
  remind_end_date: string | null;
  remind_offsets: number[];
  can_edit: boolean;
};

export type CalendarDay = {
  name: string | null;
  is_holiday: boolean;
  holiday_category: string | null;
  description: string | null;
};

// 生日設定：僅支援每年循環的生日提醒（姓名＋月/日）。
// 2026-11-26：remind_offsets 可複選「14／7／3／當天」天前推播。
// 2026-11-26：audience_mode／audience_user_ids 決定推播對象（僅限自己／自行選擇／所有人）。
export type BirthdayAudienceMode = "self" | "selected" | "everyone";

export type Birthday = {
  id: number;
  owner_user_id: number;
  name: string;
  birth_month: number;
  birth_day: number;
  remind_offsets: number[];
  audience_mode: BirthdayAudienceMode;
  audience_user_ids: number[];
  can_edit: boolean;
};

export type FamilyUser = {
  id: number;
  role: string;
  user_id: string;
  display_name: string;
};

export type FinanceAnalytics = {
  has_any_data: boolean;
  daily: Array<{ date: string; expense: number; income: number }>;
  expense_categories: Array<{ label: string; value: number }>;
  expense_total: number;
  income_total: number;
  records: Array<RecordItem>;
  latest_record: RecordItem | null;
};

// 2026-11-26：GoalItem／goals／goal_summary 已從 Finance／Body 分析頁移除（見
// docs/ADR/discuss/robinson.md），但收藏清單（collectionApi.ts）回應仍含這個欄位，型別保留供其
// 沿用。
export type GoalItem = {
  id: number | null;
  goal_type: string;
  description: string;
  target_description: string;
  status: "active" | "achieved" | "cancelled" | "expired";
  target_date: string | null;
  target_value: number | null;
  current_value: number | null;
  unit: string | null;
  progress_percent: number | null;
  progress_unavailable: boolean;
  is_exceeded: boolean;
  updated_at: string | null;
  completed_at: string | null;
};

export type RecordKind = "finance" | "diet" | "exercise" | "weight";
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
  body_defaults: { height_cm: number | null; weight_kg: number | null; waist_cm: number | null };
  latest_body_record: RecordItem | null;
  latest_records: { weight: RecordItem | null; diet: RecordItem | null; exercise: RecordItem | null };
  weight_records: Array<RecordItem>;
  diet_records: Array<RecordItem>;
  exercise_records: Array<RecordItem>;
};

export type AnalyticsResponseMap = {
  body: BodyAnalytics;
  finance: FinanceAnalytics;
};

export function getDashboard(request: AuthRequest): Promise<DashboardResponse> {
  return request<DashboardResponse>("/api/app/dashboard");
}

export function getAnalytics<M extends AnalyticsModule>(
  request: AuthRequest,
  module: M,
  range: DateRange,
): Promise<AnalyticsResponseMap[M]> {
  const queryParams = new URLSearchParams();
  queryParams.set("start", range.start);
  queryParams.set("end", range.end);
  const query = queryParams.toString();
  return request<AnalyticsResponseMap[M]>(`/api/app/analytics/${module}?${query}`);
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

export type ExerciseCategory = { id: number; name: string };

export function getExerciseCategories(request: AuthRequest): Promise<{ categories: ExerciseCategory[] }> {
  return request("/api/app/exercise-categories");
}

// 待辦事項：純通知用途，無狀態概念。後端端點目前尚未建立（沿用既有 REST 慣例推測路徑），
// 需要後端補上 /api/app/todos 的 CRUD 實作。
export function getTodos(request: AuthRequest): Promise<{ items: TodoItem[] }> {
  return request("/api/app/todos");
}

export type TodoWritePayload = {
  content: string;
  remind_offsets: number[];
  recurrence_type?: TodoRecurrenceType;
  recurrence_day?: number;
  remind_start_date?: string;
  remind_end_date?: string;
};

export function createTodo(request: AuthRequest, payload: TodoWritePayload): Promise<{ id: number; message: string }> {
  return request("/api/app/todos", { method: "POST", body: JSON.stringify(payload) });
}

export function updateTodo(request: AuthRequest, id: number, payload: TodoWritePayload): Promise<{ id: number; message: string }> {
  return request(`/api/app/todos/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
}

// 行事曆（中華民國政府行政機關辦公日曆），供待辦事項的行事曆 UI 標示國定假日/補班。
export function getCalendarMonth(request: AuthRequest, year: number, month: number): Promise<{ year: number; month: number; days: Record<string, CalendarDay> }> {
  return request(`/api/app/calendar?year=${year}&month=${month}`);
}

export function deleteTodo(request: AuthRequest, id: number): Promise<{ message: string }> {
  return request(`/api/app/todos/${id}`, { method: "DELETE" });
}

// 生日設定：僅支援每年循環的生日（姓名＋月/日）。沿用既有 important-days 端點，
// 但 payload 已簡化為只有 name/birth_month/birth_day。
export function getBirthdays(request: AuthRequest): Promise<{ items: Birthday[]; users: FamilyUser[] }> {
  return request("/api/app/important-days");
}

export type BirthdayPayload = {
  name: string;
  birth_month: number;
  birth_day: number;
  remind_offsets: number[];
  audience_mode: BirthdayAudienceMode;
  audience_user_ids: number[];
};

export function createBirthday(request: AuthRequest, payload: BirthdayPayload): Promise<{ id: number; message: string }> {
  return request("/api/app/important-days", { method: "POST", body: JSON.stringify(payload) });
}

export function updateBirthday(request: AuthRequest, id: number, payload: BirthdayPayload): Promise<{ id: number; message: string }> {
  return request(`/api/app/important-days/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function deleteBirthday(request: AuthRequest, id: number): Promise<{ message: string }> {
  return request(`/api/app/important-days/${id}`, { method: "DELETE" });
}
