/** Shapes for `/api/v1/products/label-batches/` (Phase 5). */

import type { UnitStatus } from "@/features/serialized-units/types";

export const BATCH_STATUSES = ["PENDING", "READY", "FAILED"] as const;
export type BatchStatus = (typeof BATCH_STATUSES)[number];

/** A unit status a batch may be generated as. */
export const INITIAL_STATUSES = ["AVAILABLE", "GENERATED"] as const;
export type InitialStatus = (typeof INITIAL_STATUSES)[number];

export interface LabelBatch {
  id: number;
  variant: number;
  variant_sku: string;
  product_id: number;
  product_name: string;
  location: number;
  location_name: string;
  quantity: number;
  unit_count: number;
  initial_status: UnitStatus;
  label_size: number;
  label_size_code: string;
  label_size_name: string;
  barcode_type: string;
  include_product_name: boolean;
  include_variant: boolean;
  include_sku: boolean;
  include_mrp: boolean;
  include_selling_price: boolean;
  custom_text: string;
  status: BatchStatus;
  pdf_url: string | null;
  pdf_generated_at: string | null;
  error_message: string;
  created_by: number | null;
  created_by_email: string | null;
  created_at: string;
  updated_at: string;
}

export interface LabelBatchDetail extends LabelBatch {
  serials: string[];
}

export interface NextSerial {
  serial_number: string;
  sequence: number;
}

export interface LabelBatchCreateInput {
  variant: number;
  location: number;
  quantity: number;
  initial_status?: InitialStatus;
  label_size: number;
  include_product_name?: boolean;
  include_variant?: boolean;
  include_sku?: boolean;
  include_mrp?: boolean;
  include_selling_price?: boolean;
  custom_text?: string;
}
