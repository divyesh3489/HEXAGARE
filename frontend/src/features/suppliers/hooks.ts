import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { suppliersApi, suppliersKeys, type SupplierQuery } from "./api";
import type { SupplierWriteBody } from "./types";

export function useSuppliers(query: SupplierQuery = {}) {
  return useQuery({
    queryKey: suppliersKeys.list(query),
    queryFn: () => suppliersApi.list(query),
    placeholderData: keepPreviousData,
  });
}

export function useSupplier(id: number | undefined) {
  return useQuery({
    queryKey: suppliersKeys.detail(id ?? -1),
    queryFn: () => suppliersApi.get(id as number),
    enabled: id !== undefined,
  });
}

export function useSupplierMutations() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["suppliers"] });
  return {
    create: useMutation({ mutationFn: suppliersApi.create, onSuccess: invalidate }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: number; body: Partial<SupplierWriteBody> }) =>
        suppliersApi.update(id, body),
      onSuccess: invalidate,
    }),
    remove: useMutation({ mutationFn: suppliersApi.remove, onSuccess: invalidate }),
  };
}
