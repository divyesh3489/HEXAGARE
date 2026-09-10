import type { BadgeProps } from "@/components/ui/badge";
import type { AlertType, StockStatus, TransferStatus } from "./types";

type BadgeVariant = NonNullable<BadgeProps["variant"]>;

const STATUS_VARIANTS: Record<string, BadgeVariant> = {
  AVAILABLE: "default",
  GENERATED: "muted",
  RESERVED: "secondary",
  IN_TRANSIT: "secondary",
  RETURNED: "secondary",
  SOLD: "outline",
  DAMAGED: "destructive",
  LOST: "destructive",
  CANCELLED: "muted",
};

export function stockStatusVariant(status: StockStatus | string): BadgeVariant {
  return STATUS_VARIANTS[status] ?? "muted";
}

const TRANSFER_VARIANTS: Record<TransferStatus, BadgeVariant> = {
  OPEN: "secondary",
  COMPLETED: "default",
  CANCELLED: "muted",
};

export function transferStatusVariant(status: TransferStatus): BadgeVariant {
  return TRANSFER_VARIANTS[status] ?? "muted";
}

export const ALERT_LABELS: Record<AlertType, string> = {
  out_of_stock: "Out of stock",
  low_stock: "Low stock",
  overstock: "Overstock",
  balance_mismatch: "Cache mismatch",
};

export function alertVariant(type: AlertType): BadgeVariant {
  if (type === "out_of_stock") return "destructive";
  if (type === "low_stock") return "secondary";
  if (type === "overstock") return "outline";
  return "muted";
}
