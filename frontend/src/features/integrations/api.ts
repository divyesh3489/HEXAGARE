import { api, apiRequest, type Paginated } from "@/api/client";
import type { AmazonFeeConfig, AmazonSkuMapping, ImportBatchDetail, ImportBatchListItem } from "./types";

const BASE = "/integrations/amazon";

function qs(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export interface ImportBatchQuery {
  [key: string]: string | number | undefined;
  page?: number;
  page_size?: number;
}

export const amazonImportsApi = {
  list: (query: ImportBatchQuery = {}) =>
    api.get<Paginated<ImportBatchListItem>>(`${BASE}/imports/${qs(query)}`),
  detail: (id: number) => api.get<ImportBatchDetail>(`${BASE}/imports/${id}/`),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return apiRequest<ImportBatchDetail>(`${BASE}/imports/`, { method: "POST", body: form });
  },
};

export interface SkuMappingQuery {
  [key: string]: string | number | undefined;
  page?: number;
  page_size?: number;
  search?: string;
}

export const amazonSkuMappingsApi = {
  list: (query: SkuMappingQuery = {}) =>
    api.get<Paginated<AmazonSkuMapping>>(`${BASE}/sku-mappings/${qs({ page_size: 200, ...query })}`),
  create: (body: { amazon_sku: string; variant: number }) =>
    api.post<AmazonSkuMapping>(`${BASE}/sku-mappings/`, body),
  update: (id: number, body: Partial<Pick<AmazonSkuMapping, "amazon_sku" | "variant" | "is_active">>) =>
    api.patch<AmazonSkuMapping>(`${BASE}/sku-mappings/${id}/`, body),
  remove: (id: number) => api.delete<void>(`${BASE}/sku-mappings/${id}/`),
};

export const amazonFeeConfigApi = {
  list: () => api.get<Paginated<AmazonFeeConfig>>(`${BASE}/fee-config/${qs({ page_size: 200 })}`),
  create: (
    body: Pick<
      AmazonFeeConfig,
      | "fee_name"
      | "fee_type"
      | "value"
      | "sales_channel"
      | "effective_from"
    > &
      Partial<Pick<AmazonFeeConfig, "applicable_category" | "applicable_product" | "effective_to" | "is_active">>,
  ) => api.post<AmazonFeeConfig>(`${BASE}/fee-config/`, body),
  update: (id: number, body: Partial<AmazonFeeConfig>) =>
    api.patch<AmazonFeeConfig>(`${BASE}/fee-config/${id}/`, body),
  remove: (id: number) => api.delete<void>(`${BASE}/fee-config/${id}/`),
};

export const integrationsKeys = {
  imports: (query: ImportBatchQuery) => ["integrations", "amazon", "imports", query] as const,
  import: (id: number) => ["integrations", "amazon", "import", id] as const,
  skuMappings: (query: SkuMappingQuery) => ["integrations", "amazon", "sku-mappings", query] as const,
  feeConfigs: () => ["integrations", "amazon", "fee-config"] as const,
};
