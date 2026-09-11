import type { BadgeProps } from "@/components/ui/badge";
import type { PurchaseOrderStatus } from "./types";

type BadgeVariant = NonNullable<BadgeProps["variant"]>;

const STATUS_VARIANTS: Record<PurchaseOrderStatus, BadgeVariant> = {
  DRAFT: "outline",
  ORDERED: "secondary",
  PARTIALLY_RECEIVED: "secondary",
  RECEIVED: "default",
  CANCELLED: "destructive",
};

export function purchaseOrderStatusVariant(status: PurchaseOrderStatus | string): BadgeVariant {
  return STATUS_VARIANTS[status as PurchaseOrderStatus] ?? "muted";
}
