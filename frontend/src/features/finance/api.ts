import { api } from "@/api/client";
import type { FinanceSummary, UnitProfit } from "./types";

const BASE = "/expenses/finance";

function qs(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export interface DateRangeQuery {
  [key: string]: string | undefined;
  date_from: string;
  date_to: string;
  channel?: string;
}

export const financeApi = {
  summary: (query: DateRangeQuery) =>
    api.get<FinanceSummary>(`${BASE}/summary/${qs(query)}`),
  byChannel: (query: Omit<DateRangeQuery, "channel">) =>
    api.get<FinanceSummary[]>(`${BASE}/by-channel/${qs(query)}`),
  unitProfit: (unitId: number) => api.get<UnitProfit>(`${BASE}/units/${unitId}/profit/`),
};

export const financeKeys = {
  summary: (query: DateRangeQuery) => ["finance", "summary", query] as const,
  byChannel: (query: Omit<DateRangeQuery, "channel">) => ["finance", "by-channel", query] as const,
  unitProfit: (unitId: number) => ["finance", "unit-profit", unitId] as const,
};
