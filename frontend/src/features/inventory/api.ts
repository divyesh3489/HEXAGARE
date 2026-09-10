import { api, type Paginated } from "@/api/client";
import type {
  InventoryAlert,
  InventoryOverview,
  InventoryTransaction,
  LocationOption,
  StockTransfer,
} from "./types";

const BASE = "/inventory";

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export interface OverviewQuery {
  [key: string]: string | number | undefined;
  variant?: number;
  location?: number;
  product?: number;
}

export interface LedgerQuery {
  [key: string]: string | number | undefined;
  page?: number;
  page_size?: number;
  search?: string;
  variant?: number;
  location?: number;
  status?: string;
  kind?: string;
  serialized_unit?: number;
}

export const inventoryApi = {
  overview: (query: OverviewQuery = {}) =>
    api.get<InventoryOverview>(`${BASE}/overview/${qs(query)}`),
  alerts: (query: { variant?: number; location?: number; reconcile?: boolean } = {}) =>
    api.get<InventoryAlert[]>(
      `${BASE}/alerts/${qs({
        variant: query.variant,
        location: query.location,
        reconcile: query.reconcile === false ? "false" : undefined,
      })}`,
    ),
  ledger: (query: LedgerQuery = {}) =>
    api.get<Paginated<InventoryTransaction>>(`${BASE}/transactions/${qs(query)}`),
  locations: () =>
    api.get<Paginated<LocationOption>>(`${BASE}/locations/${qs({ page_size: 100 })}`),
};

export const transfersApi = {
  list: (query: { page?: number; page_size?: number; status?: string } = {}) =>
    api.get<Paginated<StockTransfer>>(
      `${BASE}/transfers/${qs({
        page: query.page,
        page_size: query.page_size,
        status: query.status,
      })}`,
    ),
  get: (id: number) => api.get<StockTransfer>(`${BASE}/transfers/${id}/`),
  create: (body: { from_location: number; to_location: number; note?: string }) =>
    api.post<StockTransfer>(`${BASE}/transfers/`, body),
  scan: (id: number, serial: string) =>
    api.post<StockTransfer>(`${BASE}/transfers/${id}/scan/`, { serial }),
  receive: (id: number) => api.post<StockTransfer>(`${BASE}/transfers/${id}/receive/`),
  cancel: (id: number) => api.post<StockTransfer>(`${BASE}/transfers/${id}/cancel/`),
};

export const inventoryKeys = {
  overview: (query: OverviewQuery) => ["inventory", "overview", query] as const,
  alerts: (query: object) => ["inventory", "alerts", query] as const,
  ledger: (query: LedgerQuery) => ["inventory", "ledger", query] as const,
  locations: () => ["inventory", "locations"] as const,
  transfers: (query: object) => ["inventory", "transfers", "list", query] as const,
  transfer: (id: number) => ["inventory", "transfers", "detail", id] as const,
};
