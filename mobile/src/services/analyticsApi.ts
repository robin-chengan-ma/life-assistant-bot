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
  };
};

export type DateRange = { start: string; end: string };
export type AuthRequest = <T>(path: string, options?: RequestInit) => Promise<T>;

// 待辦事項：純粹的一次性提醒，只有日期與文字內容，沒有狀態／完成概念。
export type TodoItem = {
  id: number;
  owner_user_id: number;
  content: string;
  remind_date: string;
  can_edit: boolean;
};

// 生日設定：僅支援每年循環的生日提醒（姓名＋月/日）。
export type Birthday = {
  id: number;
  owner_user_id: number;
  name: string;
  birth_month: number;
  birth_day: number;
  can_edit: boolean;
};

export type FinanceAnalytics = {
  has_any_data: boolean;
  daily: Array<{ date: string; expense: number; income: number }>;
  expense_categories: Array<{ label: string; value: number }>;
  expense_total: number;
  income_total: number;
  records: Array<RecordItem>;
  latest_record: RecordItem | null;
  goals: GoalItem[];
  goal_summary: GoalItem | null;
};

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
  goals: GoalItem[];
  goal_summary: GoalItem | null;
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

export function createTodo(request: AuthRequest, payload: { content: string; remind_date: string }): Promise<{ id: number; message: string }> {
  return request("/api/app/todos", { method: "POST", body: JSON.stringify(payload) });
}

export function updateTodo(request: AuthRequest, id: number, payload: { content: string; remind_date: string }): Promise<{ id: number; message: string }> {
  return request(`/api/app/todos/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function deleteTodo(request: AuthRequest, id: number): Promise<{ message: string }> {
  return request(`/api/app/todos/${id}`, { method: "DELETE" });
}

// 生日設定：僅支援每年循環的生日（姓名＋月/日）。沿用既有 important-days 端點，
// 但 payload 已簡化為只有 name/birth_month/birth_day。
export function getBirthdays(request: AuthRequest): Promise<{ items: Birthday[] }> {
  return request("/api/app/important-days");
}

export function createBirthday(request: AuthRequest, payload: { name: string; birth_month: number; birth_day: number }): Promise<{ id: number; message: string }> {
  return request("/api/app/important-days", { method: "POST", body: JSON.stringify(payload) });
}

export function updateBirthday(request: AuthRequest, id: number, payload: { name: string; birth_month: number; birth_day: number }): Promise<{ id: number; message: string }> {
  return request(`/api/app/important-days/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function deleteBirthday(request: AuthRequest, id: number): Promise<{ message: string }> {
  return request(`/api/app/important-days/${id}`, { method: "DELETE" });
}
