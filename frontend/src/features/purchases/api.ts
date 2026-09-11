import { api, type Paginated } from "@/api/client";
import type {
  PurchaseOrder,
  PurchaseOrderCreateBody,
  PurchaseOrderLineInput,
  PurchaseOrderListItem,
  PurchaseOrderPaymentInput,
  ReceiveStockEntry,
} from "./types";

const BASE = "/purchases";

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export interface PurchaseOrderQuery {
  [key: string]: string | number | undefined;
  page?: number;
  page_size?: number;
  supplier?: number;
  status?: string;
}

export const purchaseOrdersApi = {
  list: (query: PurchaseOrderQuery = {}) =>
    api.get<Paginated<PurchaseOrderListItem>>(`${BASE}/orders/${qs(query)}`),
  get: (id: number) => api.get<PurchaseOrder>(`${BASE}/orders/${id}/`),
  create: (body: PurchaseOrderCreateBody) => api.post<PurchaseOrder>(`${BASE}/orders/`, body),
  addLine: (orderId: number, body: PurchaseOrderLineInput) =>
    api.post<PurchaseOrder>(`${BASE}/orders/${orderId}/lines/`, body),
  updateLine: (orderId: number, lineId: number, body: Partial<PurchaseOrderLineInput>) =>
    api.patch<PurchaseOrder>(`${BASE}/orders/${orderId}/lines/${lineId}/`, body),
  removeLine: (orderId: number, lineId: number) =>
    api.delete<PurchaseOrder>(`${BASE}/orders/${orderId}/lines/${lineId}/`),
  place: (orderId: number) => api.post<PurchaseOrder>(`${BASE}/orders/${orderId}/place/`),
  receive: (orderId: number, receipts: ReceiveStockEntry[]) =>
    api.post<PurchaseOrder>(`${BASE}/orders/${orderId}/receive/`, { receipts }),
  recordPayment: (orderId: number, body: PurchaseOrderPaymentInput) =>
    api.post<PurchaseOrder>(`${BASE}/orders/${orderId}/payments/`, body),
  cancel: (orderId: number) => api.post<PurchaseOrder>(`${BASE}/orders/${orderId}/cancel/`),
};

export const purchaseOrdersKeys = {
  list: (query: PurchaseOrderQuery) => ["purchase-orders", "list", query] as const,
  detail: (id: number) => ["purchase-orders", "detail", id] as const,
};
