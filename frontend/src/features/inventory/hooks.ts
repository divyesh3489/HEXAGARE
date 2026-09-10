import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  inventoryApi,
  inventoryKeys,
  transfersApi,
  type LedgerQuery,
  type OverviewQuery,
} from "./api";

export function useInventoryOverview(query: OverviewQuery = {}) {
  return useQuery({
    queryKey: inventoryKeys.overview(query),
    queryFn: () => inventoryApi.overview(query),
    placeholderData: keepPreviousData,
  });
}

export function useInventoryAlerts(query: { variant?: number; location?: number } = {}) {
  return useQuery({
    queryKey: inventoryKeys.alerts(query),
    queryFn: () => inventoryApi.alerts(query),
  });
}

export function useStockLedger(query: LedgerQuery) {
  return useQuery({
    queryKey: inventoryKeys.ledger(query),
    queryFn: () => inventoryApi.ledger(query),
    placeholderData: keepPreviousData,
  });
}

export function useInventoryLocations() {
  return useQuery({
    queryKey: inventoryKeys.locations(),
    queryFn: () => inventoryApi.locations(),
    staleTime: 5 * 60 * 1000,
  });
}

export function useStockTransfers(query: { page?: number; status?: string } = {}) {
  return useQuery({
    queryKey: inventoryKeys.transfers(query),
    queryFn: () => transfersApi.list(query),
    placeholderData: keepPreviousData,
  });
}

export function useStockTransfer(id: number | undefined) {
  return useQuery({
    queryKey: inventoryKeys.transfer(id ?? -1),
    queryFn: () => transfersApi.get(id as number),
    enabled: id !== undefined && id >= 0,
  });
}

/** Create / scan / receive / cancel, all invalidating the inventory tree so the
 * overview, alerts and ledger reflect the move. */
export function useTransferMutations(id?: number) {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["inventory"] });
    if (id !== undefined) qc.invalidateQueries({ queryKey: inventoryKeys.transfer(id) });
  };
  return {
    create: useMutation({ mutationFn: transfersApi.create, onSuccess: invalidate }),
    scan: useMutation({
      mutationFn: ({ transferId, serial }: { transferId: number; serial: string }) =>
        transfersApi.scan(transferId, serial),
      onSuccess: invalidate,
    }),
    receive: useMutation({ mutationFn: transfersApi.receive, onSuccess: invalidate }),
    cancel: useMutation({ mutationFn: transfersApi.cancel, onSuccess: invalidate }),
  };
}
