/** Shapes returned by `/api/v1/integrations/amazon/` (Phase 9). */

export const IMPORT_BATCH_STATUSES = [
  "PENDING",
  "PROCESSING",
  "READY",
  "PARTIAL",
  "FAILED",
] as const;
export type ImportBatchStatus = (typeof IMPORT_BATCH_STATUSES)[number];

export interface ImportBatchListItem {
  id: number;
  status: ImportBatchStatus;
  total_rows: number;
  total_orders: number;
  orders_created: number;
  orders_updated: number;
  orders_skipped: number;
  orders_failed: number;
  created_by: number | null;
  created_by_email: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface ImportRowError {
  row?: number;
  order_id?: string;
  message: string;
}

export interface ImportBatchDetail extends ImportBatchListItem {
  error_log: ImportRowError[];
  error_message: string;
}

export interface AmazonSkuMapping {
  id: number;
  amazon_sku: string;
  variant: number;
  variant_sku: string;
  product_name: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export const AMAZON_FEE_NAMES = [
  "REFERRAL",
  "CLOSING",
  "FULFILLMENT",
  "SHIPPING",
  "ADVERTISING",
  "OTHER",
] as const;
export type AmazonFeeName = (typeof AMAZON_FEE_NAMES)[number];

export const AMAZON_FEE_TYPES = ["PERCENTAGE", "FIXED"] as const;
export type AmazonFeeType = (typeof AMAZON_FEE_TYPES)[number];

export interface AmazonFeeConfig {
  id: number;
  fee_name: AmazonFeeName;
  fee_type: AmazonFeeType;
  value: string;
  sales_channel: number;
  sales_channel_code: string;
  applicable_category: number | null;
  applicable_category_name: string | null;
  applicable_product: number | null;
  applicable_product_name: string | null;
  effective_from: string;
  effective_to: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}
