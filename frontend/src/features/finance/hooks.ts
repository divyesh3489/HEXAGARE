import { useQuery } from "@tanstack/react-query";

import { type DateRangeQuery, financeApi, financeKeys } from "./api";

export function useFinanceSummary(query: DateRangeQuery, enabled = true) {
  return useQuery({
    queryKey: financeKeys.summary(query),
    queryFn: () => financeApi.summary(query),
    enabled,
  });
}

export function useFinanceByChannel(query: Omit<DateRangeQuery, "channel">, enabled = true) {
  return useQuery({
    queryKey: financeKeys.byChannel(query),
    queryFn: () => financeApi.byChannel(query),
    enabled,
  });
}

export function useUnitProfit(unitId: number | undefined, enabled: boolean) {
  return useQuery({
    queryKey: financeKeys.unitProfit(unitId ?? -1),
    queryFn: () => financeApi.unitProfit(unitId as number),
    enabled: enabled && unitId !== undefined,
  });
}
