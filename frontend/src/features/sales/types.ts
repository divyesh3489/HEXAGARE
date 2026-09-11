/** Shapes returned by `/api/v1/sales/` (Phase 7 core). */

export const SALE_STATUSES = [
  "DRAFT",
  "PENDING",
  "CONFIRMED",
  "RESERVED",
  "SHIPPED",
  "IN_TRANSIT",
  "DELIVERED",
  "COMPLETED",
  "CANCELLED",
  "RETURNED",
  "REFUNDED",
] as const;

export type SaleStatus = (typeof SALE_STATUSES)[number];

export interface SalesChannel {
  id: number;
  code: string;
  name: string;
  is_active: boolean;
}

export interface SaleLine {
  id: number;
  variant: number;
  sku: string;
  product_name: string;
  quantity: number;
  unit_price: string;
  tax_rate: string;
  discount_amount: string;
  gross_amount: string;
  net_amount: string;
  taxable_value: string;
  tax_amount: string;
  created_at: string;
  updated_at: string;
}

export interface SaleListItem {
  id: number;
  sales_channel: number;
  sales_channel_code: string;
  sales_channel_name: string;
  customer: number | null;
  customer_name: string | null;
  status: SaleStatus;
  external_reference: string | null;
  line_count: number;
  subtotal: string;
  discount_total: string;
  tax_total: string;
  grand_total: string;
  /** Sum of payments recorded so far (Phase 8) -- non-zero even before a
   * sale completes, while it's RESERVED/"on hold" pending the rest. */
  amount_paid: string;
  balance_due: string;
  created_at: string;
  updated_at: string;
}

export interface Sale extends SaleListItem {
  note: string;
  lines: SaleLine[];
}
