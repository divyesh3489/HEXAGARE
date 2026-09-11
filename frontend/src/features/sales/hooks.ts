import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { salesApi, salesKeys, type SalesQuery } from "./api";

export function useSalesChannels() {
  return useQuery({
    queryKey: salesKeys.channels(),
    queryFn: () => salesApi.channels(),
    staleTime: 5 * 60 * 1000,
  });
}

export function useSales(query: SalesQuery) {
  return useQuery({
    queryKey: salesKeys.list(query),
    queryFn: () => salesApi.list(query),
    placeholderData: keepPreviousData,
  });
}
