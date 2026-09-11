import { api, type Paginated } from "@/api/client";
import type { Return, ReturnCreateInput, ReturnListItem, ReturnResolveResult } from "./types";

const BASE = "/billing/returns";

function qs(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export interface ReturnQuery {
  [key: string]: string | number | undefined;
  page?: number;
  page_size?: number;
  sale?: number;
}

export const returnsApi = {
  resolve: (code: string) =>
    api.get<ReturnResolveResult>(`${BASE}/resolve/${qs({ code })}`),
  list: (query: ReturnQuery = {}) => api.get<Paginated<ReturnListItem>>(`${BASE}/${qs(query)}`),
  get: (id: number) => api.get<Return>(`${BASE}/${id}/`),
  create: (input: ReturnCreateInput) => api.post<Return>(`${BASE}/`, input),
  inspect: (returnId: number, returnUnitId: number, condition: "RESELLABLE" | "DAMAGED") =>
    api.post<Return>(`${BASE}/${returnId}/units/${returnUnitId}/inspect/`, { condition }),
};

export const returnsKeys = {
  list: (query: ReturnQuery) => ["returns", "list", query] as const,
  detail: (id: number) => ["returns", "detail", id] as const,
};
