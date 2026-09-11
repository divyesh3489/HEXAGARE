/** Shapes returned by `/api/v1/customers/` (Phase 11). */

export const CUSTOMER_TYPES = ["REGISTERED", "WALK_IN"] as const;

export type CustomerType = (typeof CUSTOMER_TYPES)[number];

export interface CustomerListItem {
  id: number;
  name: string;
  phone: string;
  email: string;
  type: CustomerType;
  created_at: string;
}

export interface CustomerSale {
  id: number;
  sales_channel_name: string;
  status: string;
  grand_total: string;
  balance_due: string;
  created_at: string;
}

export interface CustomerSerialUnit {
  id: number;
  serial_number: string;
  status: string;
  sku: string;
  product_name: string;
}

export interface Customer extends CustomerListItem {
  address: string;
  gstin: string;
  notes: string;
  updated_at: string;
  total_purchases: string;
  total_refunds: string;
  outstanding_amount: string;
  sales: CustomerSale[];
  serial_numbers: CustomerSerialUnit[];
}

export interface CustomerWriteBody {
  name: string;
  phone?: string;
  email?: string;
  address?: string;
  gstin?: string;
  notes?: string;
  type?: CustomerType;
}
