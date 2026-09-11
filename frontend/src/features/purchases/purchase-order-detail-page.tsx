import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useHasPermission } from "@/hooks/use-auth";
import { usePurchaseOrder, usePurchaseOrderMutations } from "./hooks";
import { purchaseOrderStatusVariant } from "./status";

const selectClass =
  "h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

function rupees(value: string): string {
  return `₹${Number(value).toLocaleString("en-IN")}`;
}

export function PurchaseOrderDetailPage() {
  const { orderId } = useParams();
  const canManage = useHasPermission()("purchases.manage");
  const canReceive = useHasPermission()("purchases_receiving");
  const id = Number(orderId);

  const { data: order, isPending, error } = usePurchaseOrder(id);
  const { place, cancel, recordPayment } = usePurchaseOrderMutations();

  const [payMethod, setPayMethod] = useState("BANK_TRANSFER");
  const [payAmount, setPayAmount] = useState("");
  const [payError, setPayError] = useState<string | null>(null);

  if (isPending) {
    return (
      <div className="mx-auto max-w-4xl">
        <PageHeader title="Purchase order" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error || !order) {
    return (
      <div className="mx-auto max-w-4xl">
        <PageHeader title="Purchase order" />
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            Couldn&apos;t load this purchase order.
          </CardContent>
        </Card>
      </div>
    );
  }

  const submitPayment = async () => {
    setPayError(null);
    try {
      await recordPayment.mutateAsync({
        orderId: id,
        body: { method: payMethod, amount: payAmount },
      });
      setPayAmount("");
    } catch (err) {
      setPayError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Could not record the payment.",
      );
    }
  };

  const receivable = order.status === "ORDERED" || order.status === "PARTIALLY_RECEIVED";
  const cancellable = ["DRAFT", "ORDERED", "PARTIALLY_RECEIVED"].includes(order.status);

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title={`Purchase Order #${order.id}`}
        description={order.supplier_name}
        actions={
          <div className="flex gap-2">
            {canManage && order.status === "DRAFT" && (
              <Button onClick={() => place.mutate(id)} disabled={place.isPending}>
                Place order
              </Button>
            )}
            {canReceive && receivable && (
              <Button asChild variant="outline">
                <Link to={`/purchases/receive?order=${order.id}`}>Receive stock</Link>
              </Button>
            )}
            {canManage && cancellable && (
              <Button
                variant="outline"
                disabled={cancel.isPending}
                onClick={() => {
                  if (confirm("Cancel this purchase order?")) cancel.mutate(id);
                }}
              >
                Cancel
              </Button>
            )}
          </div>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Badge variant={purchaseOrderStatusVariant(order.status)}>{order.status}</Badge>
        {order.reference && (
          <span className="text-sm text-muted-foreground">Ref: {order.reference}</span>
        )}
        {order.invoice_number && (
          <span className="text-sm text-muted-foreground">
            Invoice: {order.invoice_number}
          </span>
        )}
      </div>

      <div className="mb-4 grid gap-4 sm:grid-cols-4">
        <Card>
          <CardContent className="py-4">
            <p className="text-xs uppercase tracking-wider text-muted-foreground">Subtotal</p>
            <p className="text-lg font-semibold">{rupees(order.subtotal)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4">
            <p className="text-xs uppercase tracking-wider text-muted-foreground">Tax</p>
            <p className="text-lg font-semibold">{rupees(order.tax_total)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4">
            <p className="text-xs uppercase tracking-wider text-muted-foreground">Grand total</p>
            <p className="text-lg font-semibold">{rupees(order.grand_total)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4">
            <p className="text-xs uppercase tracking-wider text-muted-foreground">Balance due</p>
            <p className="text-lg font-semibold">{rupees(order.balance_due)}</p>
          </CardContent>
        </Card>
      </div>

      <Card className="mb-4">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Lines</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-2 font-medium">SKU</th>
                  <th className="px-4 py-2 font-medium">Product</th>
                  <th className="px-4 py-2 text-right font-medium">Ordered</th>
                  <th className="px-4 py-2 text-right font-medium">Received</th>
                  <th className="px-4 py-2 text-right font-medium">Unit price</th>
                  <th className="px-4 py-2 text-right font-medium">Net</th>
                </tr>
              </thead>
              <tbody>
                {order.lines.map((line) => (
                  <tr key={line.id} className="border-b last:border-0">
                    <td className="px-4 py-2 font-mono text-xs">{line.sku}</td>
                    <td className="px-4 py-2">{line.product_name}</td>
                    <td className="px-4 py-2 text-right">{line.quantity_ordered}</td>
                    <td className="px-4 py-2 text-right">{line.quantity_received}</td>
                    <td className="px-4 py-2 text-right">₹{line.unit_price}</td>
                    <td className="px-4 py-2 text-right">{rupees(line.net_amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Card className="mb-4">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Payments</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {order.payments.length === 0 ? (
            <p className="text-sm text-muted-foreground">No payments recorded yet.</p>
          ) : (
            <table className="w-full text-sm">
              <tbody>
                {order.payments.map((p) => (
                  <tr key={p.id} className="border-b last:border-0">
                    <td className="py-2">{p.method}</td>
                    <td className="py-2">{p.type}</td>
                    <td className="py-2 text-right">{rupees(p.amount)}</td>
                    <td className="py-2 whitespace-nowrap text-right text-muted-foreground">
                      {new Date(p.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {canManage && (
            <div className="flex flex-wrap items-end gap-3 border-t pt-4">
              <div className="flex flex-col gap-1.5">
                <Label>Method</Label>
                <select
                  value={payMethod}
                  onChange={(e) => setPayMethod(e.target.value)}
                  className={selectClass}
                >
                  <option value="CASH">Cash</option>
                  <option value="UPI">UPI</option>
                  <option value="CARD">Card</option>
                  <option value="BANK_TRANSFER">Bank transfer</option>
                  <option value="CREDIT">Credit / due</option>
                </select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Amount</Label>
                <input
                  type="number"
                  step="0.01"
                  min={0}
                  value={payAmount}
                  onChange={(e) => setPayAmount(e.target.value)}
                  className={selectClass}
                />
              </div>
              <Button
                onClick={submitPayment}
                disabled={recordPayment.isPending || !payAmount}
              >
                Record payment
              </Button>
              {payError && <p className="text-sm text-destructive">{payError}</p>}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
