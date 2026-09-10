/** Shapes returned by `/api/v1/inventory/` (Phase 4 ledger). */

export const STOCK_STATUSES = [
  "GENERATED",
  "AVAILABLE",
  "RESERVED",
  "IN_TRANSIT",
  "SOLD",
  "RETURNED",
  "DAMAGED",
  "LOST",
  "CANCELLED",
] as const;

export type StockStatus = (typeof STOCK_STATUSES)[number];

export interface OverviewRow {
  variant: number;
  sku: string;
  product_id: number;
  product_name: string;
  location: number;
  location_name: string;
  status: StockStatus;
  quantity: number;
}

export interface InventoryOverview {
  computed_from: string;
  rows: OverviewRow[];
  totals_by_status: Partial<Record<StockStatus, number>>;
  cache_matches: boolean;
}

export type AlertType =
  | "out_of_stock"
  | "low_stock"
  | "overstock"
  | "balance_mismatch";

export interface InventoryAlert {
  type: AlertType;
  variant: { id: number; sku: string; product_name: string };
  location: { id: number; name: string } | null;
  available?: number;
  threshold?: number | null;
  min_quantity?: number;
  max_quantity?: number | null;
  status?: string;
  cached?: number;
  expected?: number;
}

export interface InventoryBalance {
  id: number;
  variant: number;
  sku: string;
  product_id: number;
  product_name: string;
  location: number;
  location_name: string;
  status: StockStatus;
  quantity: number;
  updated_at: string;
}

export interface InventoryTransaction {
  id: number;
  reference: string;
  kind: string;
  variant: number;
  sku: string;
  product_name: string;
  location: number;
  location_name: string;
  status: StockStatus;
  quantity: number;
  serialized_unit: number | null;
  serial_number: string | null;
  note: string;
  actor: number | null;
  actor_email: string | null;
  created_at: string;
}

export type TransferStatus = "OPEN" | "COMPLETED" | "CANCELLED";

export interface StockTransferLine {
  id: number;
  serialized_unit: number;
  serial_number: string;
  sku: string;
  product_name: string;
  unit_status: string;
  received: boolean;
  added_at: string;
}

export interface StockTransfer {
  id: number;
  reference: string;
  from_location: number;
  from_location_name: string;
  to_location: number;
  to_location_name: string;
  status: TransferStatus;
  note: string;
  created_by: number | null;
  created_by_email: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  line_count: number;
  lines: StockTransferLine[];
}

export interface LocationOption {
  id: number;
  name: string;
  code: string;
  kind: string;
  is_active: boolean;
}
