/** Shapes returned by `/api/v1/billing/returns/` (Phase 10). */

import type { PaymentMethod } from "@/features/billing/types";
import type { Sale } from "@/features/sales/types";

export const RETURN_CONDITIONS = ["PENDING", "RESELLABLE", "DAMAGED"] as const;
export type ReturnCondition = (typeof RETURN_CONDITIONS)[number];

/** Output of `GET /billing/returns/resolve/?code=` -- the preview shown
 * right after a scan, before the cashier confirms the return. */
export interface ReturnResolveResult {
  serial_number: string;
  sku: string;
  product_name: string;
  sale: number;
  sale_line: number;
  unit_price: string;
  suggested_refund_amount: string;
}

export interface ReturnUnit {
  id: number;
  serialized_unit: number;
  serial_number: string;
  sku: string;
  product_name: string;
  sale_line: number;
  refund_amount: string;
  condition: ReturnCondition;
  inspected_at: string | null;
  inspected_by: number | null;
  created_at: string;
}

export interface ReturnListItem {
  id: number;
  sale: number;
  reason: string;
  note: string;
  refund_total: string;
  unit_count: number;
  pending_count: number;
  created_by: number | null;
  created_at: string;
}

export interface Return extends ReturnListItem {
  sale_detail: Sale;
  units: ReturnUnit[];
}

/** One scanned unit queued in the "New return" flow before submission. */
export interface ReturnEntryDraft {
  code: string;
  refund_amount: string;
  preview: ReturnResolveResult;
}

/** Input for `POST /billing/returns/`. */
export interface ReturnCreateInput {
  entries: { code: string; refund_amount?: string }[];
  reason: string;
  refund_method: PaymentMethod;
  note?: string;
}
