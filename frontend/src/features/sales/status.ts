import type { BadgeProps } from "@/components/ui/badge";
import type { SaleStatus } from "./types";

type BadgeVariant = NonNullable<BadgeProps["variant"]>;

const STATUS_VARIANTS: Record<SaleStatus, BadgeVariant> = {
  DRAFT: "outline",
  PENDING: "secondary",
  CONFIRMED: "secondary",
  RESERVED: "secondary",
  SHIPPED: "secondary",
  IN_TRANSIT: "secondary",
  DELIVERED: "default",
  COMPLETED: "default",
  CANCELLED: "destructive",
  RETURNED: "destructive",
  REFUNDED: "destructive",
};

export function saleStatusVariant(status: SaleStatus | string): BadgeVariant {
  return STATUS_VARIANTS[status as SaleStatus] ?? "muted";
}
