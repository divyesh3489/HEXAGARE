import { api, apiRequest } from "@/api/client";
import type { ExportFormat, ReportExport, ReportResult, ReportType } from "./types";

const BASE = "/reports";

function qs(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export type ReportQuery = Record<string, string | number | undefined>;

export const reportsApi = {
  sales: (query: ReportQuery) => api.get<ReportResult>(`${BASE}/sales/${qs(query)}`),
  inventory: (query: ReportQuery) => api.get<ReportResult>(`${BASE}/inventory/${qs(query)}`),
  serialNumbers: (query: ReportQuery) =>
    api.get<ReportResult>(`${BASE}/serial-numbers/${qs(query)}`),
  serialNumberHistory: (query: ReportQuery) =>
    api.get<ReportResult>(`${BASE}/serial-number-history/${qs(query)}`),
  products: (query: ReportQuery) => api.get<ReportResult>(`${BASE}/products/${qs(query)}`),
  financial: (query: ReportQuery) => api.get<ReportResult>(`${BASE}/financial/${qs(query)}`),
};

export interface CreateExportInput {
  report_type: ReportType;
  export_format: ExportFormat;
  filters: Record<string, unknown>;
}

export const reportExportsApi = {
  create: (body: CreateExportInput) => api.post<ReportExport>(`${BASE}/exports/`, body),
  get: (id: number) => api.get<ReportExport>(`${BASE}/exports/${id}/`),
  /** The rendered file, fetched with auth and handed back as a Blob (same
   * pattern as ``labelBatchesApi.pdf``). */
  download: (id: number) =>
    apiRequest<Blob>(`${BASE}/exports/${id}/download/`, { method: "GET", parse: "blob" }),
};

export const reportKeys = {
  sales: (query: ReportQuery) => ["reports", "sales", query] as const,
  inventory: (query: ReportQuery) => ["reports", "inventory", query] as const,
  serialNumbers: (query: ReportQuery) => ["reports", "serial-numbers", query] as const,
  serialNumberHistory: (query: ReportQuery) =>
    ["reports", "serial-number-history", query] as const,
  products: (query: ReportQuery) => ["reports", "products", query] as const,
  financial: (query: ReportQuery) => ["reports", "financial", query] as const,
  export: (id: number) => ["reports", "export", id] as const,
};
