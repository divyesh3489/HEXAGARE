/** Shapes returned by `/api/v1/billing/` (Phase 8). */

import type { Sale } from "@/features/sales/types";

export const PAYMENT_METHODS = ["CASH", "UPI", "CARD", "BANK_TRANSFER", "CREDIT"] as const;
export type PaymentMethod = (typeof PAYMENT_METHODS)[number];

export const INVOICE_STATUSES = ["PENDING", "READY", "FAILED"] as const;
export type InvoiceStatus = (typeof INVOICE_STATUSES)[number];

export interface Payment {
  id: number;
  sale: number;
  method: PaymentMethod;
  type: "PAYMENT" | "REFUND";
  amount: string;
  reference: string;
  note: string;
  created_at: string;
}

export const DELIVERY_CHANNELS = ["EMAIL", "WHATSAPP"] as const;
export type DeliveryChannel = (typeof DELIVERY_CHANNELS)[number];

export interface InvoiceDelivery {
  id: number;
  channel: DeliveryChannel;
  recipient: string;
  status: "PENDING" | "SENT" | "FAILED";
  sent_at: string | null;
  error_message: string;
  created_at: string;
}

export interface InvoiceListItem {
  id: number;
  sale: number;
  invoice_number: string;
  status: InvoiceStatus;
  subtotal: string;
  discount_total: string;
  tax_total: string;
  grand_total: string;
  amount_paid: string;
  balance_due: string;
  pdf_generated_at: string | null;
  error_message: string;
  created_at: string;
}

export interface Invoice extends InvoiceListItem {
  sale_detail: Sale;
  payments: Payment[];
  deliveries: InvoiceDelivery[];
}

/** Input for `POST /billing/checkout/`. */
export interface PaymentEntry {
  method: PaymentMethod;
  amount: string;
  reference?: string;
  note?: string;
}

/** Output of `POST /billing/checkout/` -- `invoice` is `null` when the
 * payment didn't cover the total: the sale is left `RESERVED` ("on hold"),
 * `sale.balance_due` says how much is still owed. */
export interface CheckoutResult {
  sale: Sale;
  invoice: Invoice | null;
}
