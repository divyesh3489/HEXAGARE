/** Shapes returned by `/api/v1/products/serialized-units/` (Phase 3). */

export const UNIT_STATUSES = [
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

export type UnitStatus = (typeof UNIT_STATUSES)[number];

/** Flat row from the Product Unit list. */
export interface SerializedUnit {
  id: number;
  serial_number: string;
  sequence: number;
  status: UnitStatus;
  location: number;
  location_name: string;
  location_code: string;
  variant_id: number;
  sku: string;
  variant_name: string;
  product_id: number;
  product_name: string;
  created_at: string;
}

export interface UnitEvent {
  id: number;
  from_status: string;
  to_status: string;
  location: number | null;
  location_name: string | null;
  note: string;
  actor: number | null;
  actor_email: string | null;
  created_at: string;
}

export interface UnitPricing {
  effective_selling_price: string;
  effective_mrp: string;
  effective_purchase_price: string;
  effective_tax_rate: string;
  base_price: string;
  gst_amount: string;
  cgst_amount: string;
  sgst_amount: string;
  discount_amount: string;
  discount_percent: string;
}

/** Detail / scan-lookup payload: the full chain plus pricing and history. */
export interface SerializedUnitDetail extends SerializedUnit {
  product: {
    id: number;
    name: string;
    code: string;
    category_id: number;
    category_name: string;
  };
  variant: {
    id: number;
    sku: string;
    name: string;
    code: string;
    effective_status: string;
  };
  pricing: UnitPricing;
  purchase_cost: string | null;
  allowed_transitions: UnitStatus[];
  events: UnitEvent[];
  updated_at: string;
}

export interface LocationOption {
  id: number;
  name: string;
  code: string;
  kind: string;
  is_active: boolean;
}
