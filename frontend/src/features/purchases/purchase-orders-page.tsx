import { Link } from "react-router-dom";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useHasPermission } from "@/hooks/use-auth";
import { usePurchaseOrders } from "./hooks";
import { purchaseOrderStatusVariant } from "./status";

function rupees(value: string): string {
  return `₹${Number(value).toLocaleString("en-IN")}`;
}

export function PurchaseOrdersPage() {
  const canManage = useHasPermission()("purchases.manage");
  const { data, isPending, error } = usePurchaseOrders({ page_size: 200 });
  const orders = data?.data ?? [];

  return (
    <div>
      <PageHeader
        title="Purchase Orders"
        description="Orders placed with suppliers, their status and payment balance."
        actions={
          canManage ? (
            <Button asChild>
              <Link to="/purchases/orders/new">New purchase order</Link>
            </Button>
          ) : undefined
        }
      />

      {error && <p className="text-sm text-destructive">Couldn’t load purchase orders.</p>}

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Order #</th>
                  <th className="px-4 py-3 font-medium">Supplier</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 text-right font-medium">Lines</th>
                  <th className="px-4 py-3 text-right font-medium">Total</th>
                  <th className="px-4 py-3 text-right font-medium">Balance due</th>
                  <th className="px-4 py-3 font-medium">Created</th>
                </tr>
              </thead>
              <tbody>
                {isPending && (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">
                      Loading…
                    </td>
                  </tr>
                )}
                {!isPending && orders.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-4 py-12 text-center text-muted-foreground">
                      No purchase orders yet.
                    </td>
                  </tr>
                )}
                {orders.map((order) => (
                  <tr key={order.id} className="border-b last:border-0">
                    <td className="px-4 py-3 font-mono text-xs">
                      <Link to={`/purchases/orders/${order.id}`} className="hover:underline">
                        #{order.id}
                      </Link>
                    </td>
                    <td className="px-4 py-3">{order.supplier_name}</td>
                    <td className="px-4 py-3">
                      <Badge variant={purchaseOrderStatusVariant(order.status)}>
                        {order.status}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-right">{order.line_count}</td>
                    <td className="px-4 py-3 text-right">{rupees(order.grand_total)}</td>
                    <td className="px-4 py-3 text-right">{rupees(order.balance_due)}</td>
                    <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">
                      {new Date(order.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
