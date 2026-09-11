import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

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

export function useSale(id: number | undefined) {
  return useQuery({
    queryKey: salesKeys.detail(id ?? -1),
    queryFn: () => salesApi.get(id as number),
    enabled: id !== undefined,
  });
}

/** Cart mutations for the POS/New Bill flow -- create, scan/search-add,
 * remove, cancel. Every mutation writes the fresh `Sale` straight into the
 * query cache (the API already returns the full updated cart), so the cart
 * UI never needs a manual invalidate+refetch round trip. */
export function useSaleCartMutations(id?: number) {
  const qc = useQueryClient();
  const onSale = (sale: { id: number }) => {
    qc.setQueryData(salesKeys.detail(sale.id), sale);
  };
  return {
    create: useMutation({ mutationFn: salesApi.create, onSuccess: onSale }),
    addUnit: useMutation({
      mutationFn: (body: { code: string } | { variant: number }) =>
        salesApi.addUnit(id as number, body),
      onSuccess: onSale,
    }),
    removeLine: useMutation({
      mutationFn: (lineId: number) => salesApi.removeLine(id as number, lineId),
      onSuccess: onSale,
    }),
    setCustomer: useMutation({
      mutationFn: (customer: number | null) => salesApi.setCustomer(id as number, customer),
      onSuccess: onSale,
    }),
    cancel: useMutation({
      mutationFn: () => salesApi.cancel(id as number),
      onSuccess: onSale,
    }),
  };
}
