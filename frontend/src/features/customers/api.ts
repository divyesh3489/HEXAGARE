import { api, type Paginated } from "@/api/client";
import type { Customer, CustomerListItem, CustomerWriteBody } from "./types";

const BASE = "/customers";

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export interface CustomerQuery {
  [key: string]: string | number | undefined;
  page?: number;
  page_size?: number;
  search?: string;
  type?: string;
}

export const customersApi = {
  list: (query: CustomerQuery = {}) =>
    api.get<Paginated<CustomerListItem>>(`${BASE}/${qs(query)}`),
  get: (id: number) => api.get<Customer>(`${BASE}/${id}/`),
  create: (body: CustomerWriteBody) => api.post<Customer>(`${BASE}/`, body),
  update: (id: number, body: Partial<CustomerWriteBody>) =>
    api.patch<Customer>(`${BASE}/${id}/`, body),
  remove: (id: number) => api.delete<void>(`${BASE}/${id}/`),
};

export const customersKeys = {
  list: (query: CustomerQuery) => ["customers", "list", query] as const,
  detail: (id: number) => ["customers", "detail", id] as const,
};
