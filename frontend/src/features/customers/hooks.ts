import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { customersApi, customersKeys, type CustomerQuery } from "./api";
import type { CustomerWriteBody } from "./types";

export function useCustomers(query: CustomerQuery = {}) {
  return useQuery({
    queryKey: customersKeys.list(query),
    queryFn: () => customersApi.list(query),
    placeholderData: keepPreviousData,
  });
}

export function useCustomer(id: number | undefined) {
  return useQuery({
    queryKey: customersKeys.detail(id ?? -1),
    queryFn: () => customersApi.get(id as number),
    enabled: id !== undefined,
  });
}

export function useCustomerMutations() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["customers"] });
  return {
    create: useMutation({ mutationFn: customersApi.create, onSuccess: invalidate }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: number; body: Partial<CustomerWriteBody> }) =>
        customersApi.update(id, body),
      onSuccess: invalidate,
    }),
    remove: useMutation({ mutationFn: customersApi.remove, onSuccess: invalidate }),
  };
}
