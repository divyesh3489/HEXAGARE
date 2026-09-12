import { api, type Paginated } from "@/api/client";
import type { Expense, ExpenseWriteBody } from "./types";

const BASE = "/expenses";

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export interface ExpenseQuery {
  [key: string]: string | number | undefined;
  page?: number;
  page_size?: number;
  category?: string;
  channel?: string;
  date_from?: string;
  date_to?: string;
}

export const expensesApi = {
  list: (query: ExpenseQuery = {}) => api.get<Paginated<Expense>>(`${BASE}/${qs(query)}`),
  create: (body: ExpenseWriteBody) => api.post<Expense>(`${BASE}/`, body),
  update: (id: number, body: Partial<ExpenseWriteBody>) =>
    api.patch<Expense>(`${BASE}/${id}/`, body),
  remove: (id: number) => api.delete<void>(`${BASE}/${id}/`),
};

export const expensesKeys = {
  list: (query: ExpenseQuery) => ["expenses", "list", query] as const,
};
