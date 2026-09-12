import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Download } from "lucide-react";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import { PageHeader } from "@/components/page-header";
import { ScanFrame } from "@/components/scan-frame";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useCheckout, useInvoice, useInvoicePdf } from "./hooks";
import { invoiceStatusVariant } from "./status";
import { PAYMENT_METHODS, type PaymentMethod } from "./types";

const selectClass =
  "h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

function errMsg(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.detail : err instanceof Error ? err.message : fallback;
}

/** Settles more of a receivable -- shown when `balance_due > 0` on an
 * already-completed invoice (e.g. a CREDIT sale being paid back). Posts to
 * the same checkout endpoint; the backend dispatches to `record_payment`
 * since the sale is already COMPLETED. */
function SettleBalanceForm({ saleId, balanceDue }: { saleId: number; balanceDue: string }) {
  const [method, setMethod] = useState<PaymentMethod>("CASH");
  const [amount, setAmount] = useState(balanceDue);
  const checkout = useCheckout();

  const submit = () => {
    const value = Number(amount);
    if (!(value > 0)) return;
    checkout.mutate(
      { sale: saleId, payments: [{ method, amount }] },
      {
        onSuccess: () => {
          toast.success("Payment recorded");
          setAmount("");
        },
        onError: (err) => toast.error(errMsg(err, "Couldn't record the payment")),
      },
    );
  };

  return (
    <div className="flex flex-wrap items-center gap-2 border-t pt-3">
      <select
        className={selectClass}
        value={method}
        onChange={(e) => setMethod(e.target.value as PaymentMethod)}
      >
        {PAYMENT_METHODS.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>
      <Input
        type="number"
        min="0"
        step="0.01"
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
        placeholder="Amount"
        className="w-32"
      />
      <Button size="sm" disabled={checkout.isPending || !(Number(amount) > 0)} onClick={submit}>
        {checkout.isPending ? "Recording…" : "Record payment"}
      </Button>
    </div>
  );
}

export function InvoiceDetailPage() {
  const params = useParams();
  const navigate = useNavigate();
  const invoiceId = Number(params.invoiceId);
  const valid = !Number.isNaN(invoiceId);

  const { data: invoice, isPending, error } = useInvoice(valid ? invoiceId : undefined);
  const pdf = useInvoicePdf(valid ? invoiceId : undefined, invoice?.status === "READY");

  if (isPending) {
    return (
      <div>
        <PageHeader title="Invoice" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (error || !invoice) {
    return (
      <div>
        <PageHeader title="Invoice" />
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            This invoice could not be loaded.
            <div className="mt-3">
              <Button variant="outline" size="sm" onClick={() => navigate("/sales/invoices")}>
                Back to invoices
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  const sale = invoice.sale_detail;

  return (
    <div className="space-y-6">
      <PageHeader
        title={invoice.invoice_number}
        description={`Order #${sale.id} · ${sale.sales_channel_name}`}
        actions={
          <div className="flex items-center gap-2">
            <Badge variant={invoiceStatusVariant(invoice.status)}>{invoice.status}</Badge>
            <Button variant="outline" size="sm" onClick={() => navigate("/sales/invoices")}>
              Back to invoices
            </Button>
          </div>
        }
      />

      <div className="grid gap-6 md:grid-cols-[1fr_2fr]">
        <div className="space-y-6">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Line items</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 pt-0 text-sm">
              {sale.lines.map((line) => (
                <div key={line.id} className="flex justify-between border-b py-1 last:border-0">
                  <span>
                    {line.product_name}{" "}
                    <span className="text-xs text-muted-foreground">× {line.quantity}</span>
                  </span>
                  <span>₹{line.net_amount}</span>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Totals</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Subtotal</span>
                <span>₹{invoice.subtotal}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Discount</span>
                <span>₹{invoice.discount_total}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Tax</span>
                <span>₹{invoice.tax_total}</span>
              </div>
              <div className="flex justify-between border-t pt-1 font-semibold">
                <span>Grand total</span>
                <span>₹{invoice.grand_total}</span>
              </div>
              <div className="flex justify-between pt-2">
                <span className="text-muted-foreground">Amount paid</span>
                <span>₹{invoice.amount_paid}</span>
              </div>
              {Number(invoice.balance_due) > 0 && (
                <div className="flex justify-between font-medium text-amber-600">
                  <span>Balance due</span>
                  <span>₹{invoice.balance_due}</span>
                </div>
              )}
            </CardContent>
            {Number(invoice.balance_due) > 0 && (
              <CardContent className="pt-0">
                <SettleBalanceForm saleId={sale.id} balanceDue={invoice.balance_due} />
              </CardContent>
            )}
          </Card>

          {invoice.payments.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Payments</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 pt-0 text-sm">
                {invoice.payments.map((payment) => (
                  <div key={payment.id} className="flex justify-between border-b py-1 last:border-0">
                    <span>
                      {payment.method}
                      {payment.type === "REFUND" && (
                        <span className="ml-1 text-xs text-destructive">(refund)</span>
                      )}
                    </span>
                    <span>₹{payment.amount}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Invoice PDF</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 pt-0">
            {invoice.status === "PENDING" && (
              <ScanFrame
                message="Rendering the PDF… this page will update automatically."
                className="aspect-video rounded-md"
              />
            )}

            {invoice.status === "FAILED" && (
              <Alert variant="destructive">
                <AlertTitle>PDF generation failed</AlertTitle>
                <AlertDescription>
                  {invoice.error_message || "The invoice could not be rendered."} The sale is
                  still completed — the units were sold and payment recorded.
                </AlertDescription>
              </Alert>
            )}

            {invoice.status === "READY" && (
              <>
                {pdf.objectUrl && (
                  <Button asChild size="sm">
                    <a href={pdf.objectUrl} download={`${invoice.invoice_number}.pdf`}>
                      <Download className="mr-1 size-4" />
                      Download
                    </a>
                  </Button>
                )}

                {pdf.isPending && <Skeleton className="h-[600px] w-full" />}
                {pdf.error && (
                  <Alert variant="destructive">
                    <AlertTitle>Couldn&apos;t load the PDF</AlertTitle>
                    <AlertDescription>
                      {pdf.error instanceof ApiError
                        ? pdf.error.detail
                        : pdf.error instanceof Error
                          ? pdf.error.message
                          : "Unknown error."}
                    </AlertDescription>
                  </Alert>
                )}
                {pdf.objectUrl && (
                  <iframe
                    src={pdf.objectUrl}
                    title={`Invoice ${invoice.invoice_number}`}
                    className="h-[600px] w-full rounded-md border"
                  />
                )}
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
