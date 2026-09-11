import { api, apiRequest, type Paginated } from "@/api/client";
import type { CheckoutResult, Invoice, InvoiceListItem, Payment, PaymentEntry } from "./types";

const BASE = "/billing";

function qs(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export interface InvoiceQuery {
  [key: string]: string | number | undefined;
  page?: number;
  page_size?: number;
  sale?: number;
  status?: string;
}

export const billingApi = {
  /** Record payment against a DRAFT/RESERVED sale. Completes it (sells the
   * units, creates the invoice) once payment covers the total -- otherwise
   * the returned `sale` is RESERVED ("on hold") and `invoice` is `null`. */
  checkout: (sale: number, payments: PaymentEntry[]) =>
    api.post<CheckoutResult>(`${BASE}/checkout/`, { sale, payments }),
  invoices: (query: InvoiceQuery = {}) =>
    api.get<Paginated<InvoiceListItem>>(`${BASE}/invoices/${qs(query)}`),
  invoice: (id: number) => api.get<Invoice>(`${BASE}/invoices/${id}/`),
  /** The rendered PDF (once `status === "READY"`), fetched with auth and
   * handed back as a Blob -- same pattern as the barcode PNG / label PDF
   * downloads. */
  invoicePdf: (id: number) =>
    apiRequest<Blob>(`${BASE}/invoices/${id}/pdf/`, { method: "GET", parse: "blob" }),
  payments: (sale?: number) =>
    api.get<Paginated<Payment>>(`${BASE}/payments/${qs({ sale, page_size: 100 })}`),
};

export const billingKeys = {
  invoices: (query: InvoiceQuery) => ["billing", "invoices", query] as const,
  invoice: (id: number) => ["billing", "invoice", id] as const,
};
