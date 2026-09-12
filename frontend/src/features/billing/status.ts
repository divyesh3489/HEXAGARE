import type { BadgeProps } from "@/components/ui/badge";
import type { InvoiceDelivery, InvoiceStatus } from "./types";

type BadgeVariant = NonNullable<BadgeProps["variant"]>;

const STATUS_VARIANTS: Record<InvoiceStatus, BadgeVariant> = {
  PENDING: "secondary",
  READY: "default",
  FAILED: "destructive",
};

export function invoiceStatusVariant(status: InvoiceStatus | string): BadgeVariant {
  return STATUS_VARIANTS[status as InvoiceStatus] ?? "muted";
}

const DELIVERY_STATUS_VARIANTS: Record<InvoiceDelivery["status"], BadgeVariant> = {
  PENDING: "secondary",
  SENT: "default",
  FAILED: "destructive",
};

export function deliveryStatusVariant(status: InvoiceDelivery["status"] | string): BadgeVariant {
  return DELIVERY_STATUS_VARIANTS[status as InvoiceDelivery["status"]] ?? "muted";
}
