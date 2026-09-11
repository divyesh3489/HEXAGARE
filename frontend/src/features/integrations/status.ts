import type { BadgeProps } from "@/components/ui/badge";
import type { ImportBatchStatus } from "./types";

type BadgeVariant = NonNullable<BadgeProps["variant"]>;

const STATUS_VARIANTS: Record<ImportBatchStatus, BadgeVariant> = {
  PENDING: "secondary",
  PROCESSING: "secondary",
  READY: "default",
  PARTIAL: "outline",
  FAILED: "destructive",
};

export function importBatchStatusVariant(status: ImportBatchStatus | string): BadgeVariant {
  return STATUS_VARIANTS[status as ImportBatchStatus] ?? "muted";
}
