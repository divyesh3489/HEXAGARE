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
  /** Start a new DRAFT sale on a channel -- the first step of the POS flow. */
  create: (salesChannel: number) =>
    api.post<Sale>(`${BASE}/`, { sales_channel: salesChannel }),
  /** Scan/search-add one exact unit to the cart (Phase 8) -- exactly one of
   * `code` or `variant`. */
  addUnit: (saleId: number, body: { code: string } | { variant: number }) =>
    api.post<Sale>(`${BASE}/${saleId}/units/`, body),
  /** Remove a whole cart line -- releases every unit bound to it. */
  removeLine: (saleId: number, lineId: number) =>
    api.delete<Sale>(`${BASE}/${saleId}/lines/${lineId}/`),
  /** Attach, change, or clear (`customer: null`) the customer on a sale. */
  setCustomer: (saleId: number, customer: number | null) =>
    api.post<Sale>(`${BASE}/${saleId}/customer/`, { customer }),
  cancel: (saleId: number) => api.post<Sale>(`${BASE}/${saleId}/cancel/`),
};

export const salesKeys = {
  channels: () => ["sales", "channels"] as const,
  list: (query: SalesQuery) => ["sales", "list", query] as const,
  detail: (id: number) => ["sales", "detail", id] as const,
};
