/** Provisional shape of a serialized unit. The real model lands in Phase 3
 * (`apps/products`); this panel renders whatever subset the API returns. */
export interface SerializedUnit {
  id: number;
  serial_number: string;
  status: string;
  location: string | null;
  sku: string | null;
  variant: string | null;
  product: string | null;
  created_at: string;
}

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
