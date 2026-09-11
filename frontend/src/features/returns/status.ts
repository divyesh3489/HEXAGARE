import type { BadgeProps } from "@/components/ui/badge";
import type { ReturnCondition } from "./types";

type BadgeVariant = NonNullable<BadgeProps["variant"]>;

const CONDITION_VARIANTS: Record<ReturnCondition, BadgeVariant> = {
  PENDING: "secondary",
  RESELLABLE: "default",
  DAMAGED: "destructive",
};

export function conditionVariant(condition: ReturnCondition | string): BadgeVariant {
  return CONDITION_VARIANTS[condition as ReturnCondition] ?? "muted";
}
