/** Shapes returned by `/api/v1/purchases/` (Phase 12). */

export const PURCHASE_ORDER_STATUSES = [
  "DRAFT",
  "ORDERED",
  "PARTIALLY_RECEIVED",
  "RECEIVED",
  "CANCELLED",
] as const;

export type PurchaseOrderStatus = (typeof PURCHASE_ORDER_STATUSES)[number];

export interface PurchaseOrderLineUnit {
  id: number;
  serialized_unit: number;
  serial_number: string;
  status: string;
  created_at: string;
}

export interface PurchaseOrderLine {
  id: number;
  variant: number;
  sku: string;
  product_name: string;
  quantity_ordered: number;
  quantity_received: number;
  quantity_pending: number;
  unit_price: string;
  tax_rate: string;
  discount_amount: string;
  gross_amount: string;
  net_amount: string;
  taxable_value: string;
  tax_amount: string;
  units: PurchaseOrderLineUnit[];
  created_at: string;
  updated_at: string;
}

export interface PurchaseOrderPayment {
  id: number;
  method: string;
  type: "PAYMENT" | "REFUND";
  amount: string;
  reference: string;
  note: string;
  created_at: string;
}

export interface PurchaseOrderListItem {
  id: number;
  supplier: number;
  supplier_name: string;
  status: PurchaseOrderStatus;
  reference: string;
  invoice_number: string;
  line_count: number;
  subtotal: string;
  discount_total: string;
  tax_total: string;
  grand_total: string;
  amount_paid: string;
  balance_due: string;
  created_at: string;
  updated_at: string;
}

export interface PurchaseOrder extends PurchaseOrderListItem {
  note: string;
  lines: PurchaseOrderLine[];
  payments: PurchaseOrderPayment[];
}

export interface PurchaseOrderLineInput {
  variant: number;
  quantity_ordered: number;
  unit_price: string;
  tax_rate?: string;
  discount_amount?: string;
}

export interface PurchaseOrderCreateBody {
  supplier: number;
  reference?: string;
  invoice_number?: string;
  note?: string;
  lines?: PurchaseOrderLineInput[];
}

export interface ReceiveStockEntry {
  line: number;
  quantity: number;
  location: number;
}

export interface PurchaseOrderPaymentInput {
  method: string;
  type?: "PAYMENT" | "REFUND";
  amount: string;
  reference?: string;
  note?: string;
}
