import { api, apiRequest, type Paginated } from "@/api/client";
import type { LocationOption, SerializedUnit, SerializedUnitDetail } from "./types";

const BASE = "/products/serialized-units";

function qs(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export interface SerializedUnitQuery {
  [key: string]: string | number | undefined;
  page?: number;
  page_size?: number;
  search?: string;
  status?: string;
  location?: number;
  variant?: number;
  product?: number;
  ordering?: string;
}

export const serializedUnitsApi = {
  list: (query: SerializedUnitQuery = {}) =>
    api.get<Paginated<SerializedUnit>>(`${BASE}/${qs(query)}`),
  get: (id: number) => api.get<SerializedUnitDetail>(`${BASE}/${id}/`),
  lookup: (code: string) =>
    api.get<SerializedUnitDetail>(`${BASE}/lookup/${qs({ code })}`),
  /** The on-demand Code128 PNG, fetched with auth and handed back as a Blob. */
  barcode: (id: number) =>
    apiRequest<Blob>(`${BASE}/${id}/barcode/`, { method: "GET", parse: "blob" }),
};

export const locationsApi = {
  list: () =>
    api.get<Paginated<LocationOption>>(`/inventory/locations/${qs({ page_size: 100 })}`),
};

export const serializedUnitKeys = {
  list: (query: SerializedUnitQuery) => ["serialized-units", "list", query] as const,
  detail: (id: number) => ["serialized-units", "detail", id] as const,
  barcode: (id: number) => ["serialized-units", "barcode", id] as const,
  locations: () => ["inventory", "locations"] as const,
};
