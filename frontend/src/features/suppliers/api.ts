import { api, type Paginated } from "@/api/client";
import type { Supplier, SupplierListItem, SupplierWriteBody } from "./types";

const BASE = "/suppliers";

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export interface SupplierQuery {
  [key: string]: string | number | undefined;
  page?: number;
  page_size?: number;
  search?: string;
}

export const suppliersApi = {
  list: (query: SupplierQuery = {}) =>
    api.get<Paginated<SupplierListItem>>(`${BASE}/${qs(query)}`),
  get: (id: number) => api.get<Supplier>(`${BASE}/${id}/`),
  create: (body: SupplierWriteBody) => api.post<Supplier>(`${BASE}/`, body),
  update: (id: number, body: Partial<SupplierWriteBody>) =>
    api.patch<Supplier>(`${BASE}/${id}/`, body),
  remove: (id: number) => api.delete<void>(`${BASE}/${id}/`),
};

export const suppliersKeys = {
  list: (query: SupplierQuery) => ["suppliers", "list", query] as const,
  detail: (id: number) => ["suppliers", "detail", id] as const,
};
