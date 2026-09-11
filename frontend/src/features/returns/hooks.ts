import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { returnsApi, returnsKeys, type ReturnQuery } from "./api";
import type { ReturnCreateInput } from "./types";

export function useReturns(query: ReturnQuery = {}) {
  return useQuery({
    queryKey: returnsKeys.list(query),
    queryFn: () => returnsApi.list(query),
    placeholderData: keepPreviousData,
  });
}

export function useReturn(id: number | undefined) {
  return useQuery({
    queryKey: returnsKeys.detail(id ?? -1),
    queryFn: () => returnsApi.get(id as number),
    enabled: id !== undefined && id >= 0,
  });
}

/** Not a `useQuery` -- resolving a scanned code is triggered per scan, not
 * something to cache/refetch, same reasoning as a one-shot lookup. */
export function useResolveReturnCode() {
  return useMutation({ mutationFn: returnsApi.resolve });
}

export function useCreateReturn() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: ReturnCreateInput) => returnsApi.create(input),
    onSuccess: (created) => {
      qc.setQueryData(returnsKeys.detail(created.id), created);
      qc.invalidateQueries({ queryKey: ["returns", "list"] });
    },
  });
}

export function useInspectReturnUnit(returnId: number | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      returnUnitId,
      condition,
    }: {
      returnUnitId: number;
      condition: "RESELLABLE" | "DAMAGED";
    }) => returnsApi.inspect(returnId as number, returnUnitId, condition),
    onSuccess: (updated) => {
      qc.setQueryData(returnsKeys.detail(updated.id), updated);
    },
  });
}
