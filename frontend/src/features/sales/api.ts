import { api, type Paginated } from "@/api/client";
import type { Sale, SaleListItem, SalesChannel } from "./types";

const BASE = "/sales";

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export interface SalesQuery {
  [key: string]: string | number | undefined;
  page?: number;
  page_size?: number;
  channel?: string;
  status?: string;
}

export const salesApi = {
  channels: () => api.get<Paginated<SalesChannel>>(`${BASE}/channels/${qs({ page_size: 100 })}`),
  list: (query: SalesQuery = {}) => api.get<Paginated<SaleListItem>>(`${BASE}/${qs(query)}`),
  get: (id: number) => api.get<Sale>(`${BASE}/${id}/`),
};

export const salesKeys = {
  channels: () => ["sales", "channels"] as const,
  list: (query: SalesQuery) => ["sales", "list", query] as const,
  detail: (id: number) => ["sales", "detail", id] as const,
};
