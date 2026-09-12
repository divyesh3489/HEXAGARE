import { useQuery } from "@tanstack/react-query";

import { type FinanceQuery, dashboardApi, dashboardKeys } from "./api";

export function useDashboardSales() {
  return useQuery({ queryKey: dashboardKeys.sales(), queryFn: dashboardApi.sales });
}

export function useDashboardInventory() {
  return useQuery({ queryKey: dashboardKeys.inventory(), queryFn: dashboardApi.inventory });
}

export function useDashboardFinance(query: FinanceQuery = {}) {
  return useQuery({
    queryKey: dashboardKeys.finance(query),
    queryFn: () => dashboardApi.finance(query),
  });
}

export function useDashboardAnalytics() {
  return useQuery({ queryKey: dashboardKeys.analytics(), queryFn: dashboardApi.analytics });
}
