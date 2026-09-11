import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { purchaseOrdersApi, purchaseOrdersKeys, type PurchaseOrderQuery } from "./api";
import type {
  PurchaseOrderLineInput,
  PurchaseOrderPaymentInput,
  ReceiveStockEntry,
} from "./types";

export function usePurchaseOrders(query: PurchaseOrderQuery = {}) {
  return useQuery({
    queryKey: purchaseOrdersKeys.list(query),
    queryFn: () => purchaseOrdersApi.list(query),
    placeholderData: keepPreviousData,
  });
}

export function usePurchaseOrder(id: number | undefined) {
  return useQuery({
    queryKey: purchaseOrdersKeys.detail(id ?? -1),
    queryFn: () => purchaseOrdersApi.get(id as number),
    enabled: id !== undefined,
  });
}

export function usePurchaseOrderMutations() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["purchase-orders"] });
  return {
    create: useMutation({ mutationFn: purchaseOrdersApi.create, onSuccess: invalidate }),
    addLine: useMutation({
      mutationFn: ({ orderId, body }: { orderId: number; body: PurchaseOrderLineInput }) =>
        purchaseOrdersApi.addLine(orderId, body),
      onSuccess: invalidate,
    }),
    updateLine: useMutation({
      mutationFn: ({
        orderId,
        lineId,
        body,
      }: {
        orderId: number;
        lineId: number;
        body: Partial<PurchaseOrderLineInput>;
      }) => purchaseOrdersApi.updateLine(orderId, lineId, body),
      onSuccess: invalidate,
    }),
    removeLine: useMutation({
      mutationFn: ({ orderId, lineId }: { orderId: number; lineId: number }) =>
        purchaseOrdersApi.removeLine(orderId, lineId),
      onSuccess: invalidate,
    }),
    place: useMutation({ mutationFn: purchaseOrdersApi.place, onSuccess: invalidate }),
    receive: useMutation({
      mutationFn: ({ orderId, receipts }: { orderId: number; receipts: ReceiveStockEntry[] }) =>
        purchaseOrdersApi.receive(orderId, receipts),
      onSuccess: invalidate,
    }),
    recordPayment: useMutation({
      mutationFn: ({ orderId, body }: { orderId: number; body: PurchaseOrderPaymentInput }) =>
        purchaseOrdersApi.recordPayment(orderId, body),
      onSuccess: invalidate,
    }),
    cancel: useMutation({ mutationFn: purchaseOrdersApi.cancel, onSuccess: invalidate }),
  };
}
