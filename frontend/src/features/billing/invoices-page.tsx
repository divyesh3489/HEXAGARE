import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useInvoices } from "./hooks";
import { invoiceStatusVariant } from "./status";

const PAGE_SIZE = 20;

export function InvoicesPage() {
  const [page, setPage] = useState(1);
  const query = useMemo(() => ({ page, page_size: PAGE_SIZE }), [page]);
  const { data, isPending, isFetching, error, refetch } = useInvoices(query);
  const invoices = data?.data ?? [];
  const count = data?.meta.count ?? 0;

  return (
    <div>
      <PageHeader
        title="Invoices"
        description="Every invoice generated from a completed sale."
      />

      {error && (
        <Alert variant="destructive">
          <AlertTitle>Couldn&apos;t load invoices</AlertTitle>
          <AlertDescription className="flex flex-col items-start gap-2">
            <span>{error instanceof Error ? error.message : "Unknown error."}</span>
            <Button size="sm" variant="outline" onClick={() => refetch()}>
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {!error && (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="px-4 py-3 font-medium">Invoice #</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                    <th className="px-4 py-3 text-right font-medium">Total</th>
                    <th className="px-4 py-3 text-right font-medium">Balance due</th>
                    <th className="px-4 py-3 font-medium">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {isPending &&
                    Array.from({ length: 8 }).map((_, i) => (
                      <tr key={i} className="border-b">
                        {Array.from({ length: 5 }).map((__, j) => (
                          <td key={j} className="px-4 py-3">
                            <Skeleton className="h-4 w-16" />
                          </td>
                        ))}
                      </tr>
                    ))}

                  {!isPending && invoices.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-4 py-12 text-center text-sm text-muted-foreground">
                        No invoices yet — complete a sale from New Bill.
                      </td>
                    </tr>
                  )}

                  {invoices.map((invoice) => (
                    <tr key={invoice.id} className="border-b last:border-0">
                      <td className="px-4 py-3 font-mono text-xs">
                        <Link to={`/sales/invoices/${invoice.id}`} className="hover:underline">
                          {invoice.invoice_number}
                        </Link>
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant={invoiceStatusVariant(invoice.status)}>
                          {invoice.status}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-right font-medium">
                        ₹{Number(invoice.grand_total).toLocaleString("en-IN")}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {Number(invoice.balance_due) > 0
                          ? `₹${Number(invoice.balance_due).toLocaleString("en-IN")}`
                          : "—"}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">
                        {new Date(invoice.created_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {!error && count > PAGE_SIZE && (
        <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground">
          <span>
            {count} invoice{count === 1 ? "" : "s"}
            {isFetching ? " · updating…" : ""}
          </span>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={!data?.meta.previous}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Previous
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!data?.meta.next}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
