import { api } from "@/api/client";
import type { DashboardAnalytics, DashboardFinance, DashboardInventory, DashboardSales } from "./types";

const BASE = "/reports/dashboard";

function qs(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) search.set(key, value);
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export interface FinanceQuery {
  [key: string]: string | undefined;
  date_from?: string;
  date_to?: string;
}

export const dashboardApi = {
  sales: () => api.get<DashboardSales>(`${BASE}/sales/`),
  inventory: () => api.get<DashboardInventory>(`${BASE}/inventory/`),
  finance: (query: FinanceQuery) => api.get<DashboardFinance>(`${BASE}/finance/${qs(query)}`),
  analytics: () => api.get<DashboardAnalytics>(`${BASE}/analytics/`),
};

export const dashboardKeys = {
  sales: () => ["dashboard", "sales"] as const,
  inventory: () => ["dashboard", "inventory"] as const,
  finance: (query: FinanceQuery) => ["dashboard", "finance", query] as const,
  analytics: () => ["dashboard", "analytics"] as const,
};
