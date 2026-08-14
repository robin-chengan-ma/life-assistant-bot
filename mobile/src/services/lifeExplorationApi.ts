import type { AuthRequest } from "@/services/analyticsApi";

export type TripStatus = "planning" | "confirmed" | "completed" | "cancelled";
export type TripItem = { collection_item_id: number; sort_order: number; visit_status: "planned" | "visited" | "skipped"; title_snapshot: string; item_type: string | null; country_name: string | null; city_name: string | null; address: string | null };
export type Trip = { id: number; title: string; start_date: string | null; end_date: string | null; country_name: string; city_name: string; budget_amount: number; estimated_transport: number | null; estimated_accommodation: number | null; estimated_food: number | null; estimated_tickets: number | null; estimated_shopping: number | null; estimated_other: number | null; actual_expense: number; actual_transport: number; actual_accommodation: number; actual_food: number; actual_tickets: number; actual_shopping: number; actual_other: number; expense_difference: number; status: TripStatus; notes: string | null; items: TripItem[] };
export type TripPayload = { title: string; start_date?: string; end_date?: string; country_name: string; city_name: string; status: TripStatus; notes?: string; collection_item_ids: number[]; budget_amount?: number; estimated_transport?: number; estimated_accommodation?: number; estimated_food?: number; estimated_tickets?: number; estimated_shopping?: number; estimated_other?: number };
export type ExplorationVisit = { id: number; collection_item_id: number | null; event_type: string; title: string; start_date: string; country_name: string | null; city_name: string | null; address: string | null; source_url: string | null; notes: string | null };
export type ExplorationMarker = { latitude: number; longitude: number; title: string; visits: ExplorationVisit[] };
export type ExplorationResponse = { markers: ExplorationMarker[]; unlocated: ExplorationVisit[]; filters: { countries: string[]; cities: string[] } };
export type Achievement = { id: number; category: string; title: string; description: string | null; unlocked_on: string; creation_source: "manual" | "suggested"; cover_image_url: string | null };
export type AchievementCandidate = { id: number; category: string; title: string; description: string | null; completed_on: string };
export type AchievementResponse = { achievements: Achievement[]; candidates: AchievementCandidate[] };

export const getTrips = (request: AuthRequest): Promise<{ trips: Trip[] }> => request("/api/app/life/trips");
export const saveTrip = (request: AuthRequest, payload: TripPayload, id?: number): Promise<{ id: number; message: string }> => request(id ? `/api/app/life/trips/${id}` : "/api/app/life/trips", { method: id ? "PATCH" : "POST", body: JSON.stringify(payload) });
export const deleteTrip = (request: AuthRequest, id: number) => request(`/api/app/life/trips/${id}`, { method: "DELETE" });
export const restoreTrip = (request: AuthRequest, id: number) => request(`/api/app/life/trips/${id}/restore`, { method: "POST" });
export const completeTrip = (request: AuthRequest, id: number, visited_collection_ids: number[]) => request(`/api/app/life/trips/${id}/complete`, { method: "POST", body: JSON.stringify({ visited_collection_ids }) });
export const visitCollection = (request: AuthRequest, id: number, visited_on: string, notes?: string) => request(`/api/app/life/collections/${id}/visit`, { method: "POST", body: JSON.stringify({ visited_on, notes }) });
export const getExploration = (request: AuthRequest, filters: { country?: string; city?: string } = {}): Promise<ExplorationResponse> => { const query = new URLSearchParams(); if (filters.country) query.set("country", filters.country); if (filters.city) query.set("city", filters.city); return request(`/api/app/life/exploration${query.toString() ? `?${query}` : ""}`); };
export const updateExploration = (request: AuthRequest, id: number, payload: { visited_on: string; notes?: string; address?: string }) => request(`/api/app/life/exploration/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
export const deleteExploration = (request: AuthRequest, id: number) => request(`/api/app/life/exploration/${id}`, { method: "DELETE" });
export const restoreExploration = (request: AuthRequest, id: number) => request(`/api/app/life/exploration/${id}/restore`, { method: "POST" });
export const relocateExploration = (request: AuthRequest, id: number): Promise<{ id: number; message: string; latitude: number; longitude: number; display_name: string }> => request(`/api/app/life/exploration/${id}/relocate`, { method: "POST" });
export const getAchievements = (request: AuthRequest): Promise<AchievementResponse> => request("/api/app/life/achievements");
export const createAchievement = (request: AuthRequest, payload: { category: string; title: string; description?: string; completed_on: string; cover_image_url?: string }) => request("/api/app/life/achievements", { method: "POST", body: JSON.stringify(payload) });
export const deleteAchievement = (request: AuthRequest, id: number) => request(`/api/app/life/achievements/${id}`, { method: "DELETE" });
export const restoreAchievement = (request: AuthRequest, id: number) => request(`/api/app/life/achievements/${id}/restore`, { method: "POST" });
export const decideAchievement = (request: AuthRequest, id: number, accept: boolean) => request(`/api/app/life/achievement-candidates/${id}/decision`, { method: "POST", body: JSON.stringify({ accept }) });
