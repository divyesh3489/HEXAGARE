import { useEffect, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { salesKeys } from "@/features/sales/api";
import { billingApi, billingKeys, type InvoiceQuery } from "./api";
import type { PaymentEntry } from "./types";

export function useInvoices(query: InvoiceQuery = {}) {
  return useQuery({
    queryKey: billingKeys.invoices(query),
    queryFn: () => billingApi.invoices(query),
    placeholderData: keepPreviousData,
  });
}

/** One invoice. While the PDF is still rendering, poll every 2s -- same
 * pattern as the label-batch PDF poll. */
export function useInvoice(id: number | undefined) {
  return useQuery({
    queryKey: billingKeys.invoice(id ?? -1),
    queryFn: () => billingApi.invoice(id as number),
    enabled: id !== undefined && id >= 0,
    refetchInterval: (query) => (query.state.data?.status === "PENDING" ? 2000 : false),
  });
}

/** Records payment via `POST /billing/checkout/` -- completes/holds a
 * DRAFT/RESERVED sale, or settles more of an already-COMPLETED sale's
 * receivable, depending on its current status (the backend dispatches).
 * Writes the returned `sale`/`invoice` straight into their query caches so
 * every screen showing this sale or invoice updates without a refetch. */
export function useCheckout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ sale, payments }: { sale: number; payments: PaymentEntry[] }) =>
      billingApi.checkout(sale, payments),
    onSuccess: (result) => {
      qc.setQueryData(salesKeys.detail(result.sale.id), result.sale);
      if (result.invoice) {
        qc.setQueryData(billingKeys.invoice(result.invoice.id), result.invoice);
      }
    },
  });
}

/** The rendered invoice PDF as an object URL, once `status === "READY"` --
 * same blob-to-object-URL pattern as the label-batch PDF viewer. */
export function useInvoicePdf(id: number | undefined, ready: boolean) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["billing", "invoice-pdf", id ?? -1],
    queryFn: () => billingApi.invoicePdf(id as number),
    enabled: id !== undefined && id >= 0 && ready,
    staleTime: Infinity,
  });

  useEffect(() => {
    if (!query.data) {
      setObjectUrl(null);
      return;
    }
    const url = URL.createObjectURL(query.data);
    setObjectUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [query.data]);

  return { ...query, objectUrl };
}
