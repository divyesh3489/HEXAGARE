import { api, apiRequest, type Paginated } from "@/api/client";
import type { LabelSize } from "@/features/products/types";
import type { LocationOption } from "@/features/serialized-units/types";
import type {
  LabelBatch,
  LabelBatchCreateInput,
  LabelBatchDetail,
  NextSerial,
} from "./types";

const BASE = "/products/label-batches";

function qs(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export interface LabelBatchQuery {
  [key: string]: string | number | undefined;
  page?: number;
  page_size?: number;
  variant?: number;
  product?: number;
  status?: string;
}

export const labelBatchesApi = {
  list: (query: LabelBatchQuery = {}) =>
    api.get<Paginated<LabelBatch>>(`${BASE}/${qs(query)}`),
  get: (id: number) => api.get<LabelBatchDetail>(`${BASE}/${id}/`),
  create: (body: LabelBatchCreateInput) =>
    api.post<LabelBatchDetail>(`${BASE}/`, body),
  regenerate: (id: number) =>
    api.post<LabelBatchDetail>(`${BASE}/${id}/regenerate/`),
  nextSerial: (variantId: number) =>
    api.get<NextSerial>(`${BASE}/next-serial/${qs({ variant: variantId })}`),
  /** The rendered label sheet, fetched with auth and handed back as a Blob. */
  pdf: (id: number) =>
    apiRequest<Blob>(`${BASE}/${id}/pdf/`, { method: "GET", parse: "blob" }),
};

export const labelSizesApi = {
  list: () =>
    api.get<Paginated<LabelSize>>(
      `/products/label-sizes/${qs({ is_active: 1, page_size: 100 })}`,
    ),
};

export const labelBatchLocationsApi = {
  list: () =>
    api.get<Paginated<LocationOption>>(
      `/inventory/locations/${qs({ page_size: 100 })}`,
    ),
};

export const labelBatchKeys = {
  list: (query: LabelBatchQuery) => ["label-batches", "list", query] as const,
  detail: (id: number) => ["label-batches", "detail", id] as const,
  pdf: (id: number) => ["label-batches", "pdf", id] as const,
  nextSerial: (variantId: number) => ["label-batches", "next-serial", variantId] as const,
  labelSizes: () => ["label-sizes"] as const,
  locations: () => ["inventory", "locations"] as const,
};
