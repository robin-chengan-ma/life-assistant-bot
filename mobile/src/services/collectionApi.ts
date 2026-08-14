import type { AuthRequest } from "@/services/analyticsApi";

export type CollectionItemType = "restaurant" | "attraction" | "mountain" | "accommodation" | "activity" | "other";
export type CollectionStatus = "saved" | "added_to_trip" | "visited" | "cancelled";

export type CollectionItem = {
  id: number;
  trip_id: number | null;
  item_type: CollectionItemType;
  title: string;
  country_code: string | null;
  country_name: string | null;
  city_name: string | null;
  address: string | null;
  latitude: number | null;
  longitude: number | null;
  source_url: string | null;
  estimated_cost: number | null;
  currency_code: string;
  notes: string | null;
  status: CollectionStatus;
  visited_at: string | null;
  created_at: string;
  updated_at: string;
};

export type CollectionPayload = {
  item_type: CollectionItemType;
  title: string;
  country_code?: string;
  country_name?: string;
  city_name?: string;
  address?: string;
  source_url?: string;
  estimated_cost?: number;
  currency_code?: "TWD";
  notes?: string;
};

export type CollectionResponse = {
  items: CollectionItem[];
  summary: { total: number; saved: number; added_to_trip: number; visited: number };
  filters: { countries: string[]; cities: string[] };
};

export function getCollectionItems(
  request: AuthRequest,
  filters: { country?: string; city?: string; type?: CollectionItemType; status?: CollectionStatus } = {},
): Promise<CollectionResponse> {
  const query = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => { if (value) query.set(key, value); });
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request(`/api/app/collections${suffix}`);
}

export function createCollectionItem(
  request: AuthRequest,
  payload: CollectionPayload,
): Promise<{ id: number; message: string }> {
  return request("/api/app/collections", { method: "POST", body: JSON.stringify(payload) });
}

export function updateCollectionItem(
  request: AuthRequest,
  id: number,
  payload: CollectionPayload,
): Promise<{ id: number; message: string }> {
  return request(`/api/app/collections/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function deleteCollectionItem(request: AuthRequest, id: number): Promise<{ message: string }> {
  return request(`/api/app/collections/${id}`, { method: "DELETE" });
}

export function restoreCollectionItem(request: AuthRequest, id: number): Promise<{ message: string }> {
  return request(`/api/app/collections/${id}/restore`, { method: "POST" });
}
