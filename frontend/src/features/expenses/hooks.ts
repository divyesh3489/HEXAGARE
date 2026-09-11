import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { expensesApi, expensesKeys, type ExpenseQuery } from "./api";
import type { ExpenseWriteBody } from "./types";

export function useExpenses(query: ExpenseQuery = {}) {
  return useQuery({
    queryKey: expensesKeys.list(query),
    queryFn: () => expensesApi.list(query),
    placeholderData: keepPreviousData,
  });
}

export function useExpenseMutations() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["expenses"] });
  return {
    create: useMutation({ mutationFn: expensesApi.create, onSuccess: invalidate }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: number; body: Partial<ExpenseWriteBody> }) =>
        expensesApi.update(id, body),
      onSuccess: invalidate,
    }),
    remove: useMutation({ mutationFn: expensesApi.remove, onSuccess: invalidate }),
  };
}
