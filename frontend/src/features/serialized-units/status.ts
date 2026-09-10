import type { BadgeProps } from "@/components/ui/badge";
import type { UnitStatus } from "./types";

type BadgeVariant = NonNullable<BadgeProps["variant"]>;

const VARIANTS: Record<string, BadgeVariant> = {
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

export function statusBadgeVariant(status: UnitStatus | string): BadgeVariant {
  return VARIANTS[status] ?? "muted";
}
