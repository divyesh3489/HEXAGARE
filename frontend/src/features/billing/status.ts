import type { BadgeProps } from "@/components/ui/badge";
import type { InvoiceStatus } from "./types";

type BadgeVariant = NonNullable<BadgeProps["variant"]>;

const STATUS_VARIANTS: Record<InvoiceStatus, BadgeVariant> = {
  PENDING: "secondary",
  READY: "default",
  FAILED: "destructive",
};

export function invoiceStatusVariant(status: InvoiceStatus | string): BadgeVariant {
  return STATUS_VARIANTS[status as InvoiceStatus] ?? "muted";
}
