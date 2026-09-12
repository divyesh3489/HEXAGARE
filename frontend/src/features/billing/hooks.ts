import { useEffect, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { salesKeys } from "@/features/sales/api";
import { billingApi, billingKeys, type InvoiceQuery } from "./api";
import type { DeliveryChannel, PaymentEntry } from "./types";

export function useInvoices(query: InvoiceQuery = {}) {
  return useQuery({
    queryKey: billingKeys.invoices(query),
    queryFn: () => billingApi.invoices(query),
    placeholderData: keepPreviousData,
  });
}

/** One invoice. Polls every 2s while the PDF is still rendering (same
 * pattern as the label-batch PDF poll) or while a just-sent delivery is
 * still PENDING (the actual send happens in the Celery worker, out of band
 * from the `send/` response). */
export function useInvoice(id: number | undefined) {
  return useQuery({
    queryKey: billingKeys.invoice(id ?? -1),
    queryFn: () => billingApi.invoice(id as number),
    enabled: id !== undefined && id >= 0,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return false;
      const deliveryPending = data.deliveries.some((d) => d.status === "PENDING");
      return data.status === "PENDING" || deliveryPending ? 2000 : false;
    },
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

/** Sends the invoice over email/WhatsApp -- writes the returned invoice
 * (with its new `deliveries` entry) straight into the query cache. */
export function useSendInvoice(invoiceId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ channel, recipient }: { channel: DeliveryChannel; recipient?: string }) =>
      billingApi.sendInvoice(invoiceId, channel, recipient),
    onSuccess: (invoice) => {
      qc.setQueryData(billingKeys.invoice(invoice.id), invoice);
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
