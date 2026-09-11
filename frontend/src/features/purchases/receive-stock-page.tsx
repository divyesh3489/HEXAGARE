import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { useInventoryLocations } from "@/features/inventory/hooks";
import { usePurchaseOrder, usePurchaseOrderMutations, usePurchaseOrders } from "./hooks";

const selectClass =
  "h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

export function ReceiveStockPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const preselected = searchParams.get("order");

  const { data: ordersData } = usePurchaseOrders({ page_size: 200 });
  const receivableOrders = (ordersData?.data ?? []).filter(
    (o) => o.status === "ORDERED" || o.status === "PARTIALLY_RECEIVED",
  );

  const orderId = preselected ? Number(preselected) : undefined;
  const { data: order, isPending: orderLoading } = usePurchaseOrder(orderId);

  const { data: locationsData } = useInventoryLocations();
  const locations = (locationsData?.data ?? []).filter((l) => l.is_active);
  const [locationId, setLocationId] = useState("");

  const [quantities, setQuantities] = useState<Record<number, string>>({});
  const { receive } = usePurchaseOrderMutations();
  const [formError, setFormError] = useState<string | null>(null);

  const pendingLines = useMemo(
    () => (order?.lines ?? []).filter((line) => line.quantity_pending > 0),
    [order],
  );

  const receipts = pendingLines
    .map((line) => ({ line: line.id, quantity: Number(quantities[line.id] || 0) }))
    .filter((entry) => entry.quantity > 0);

  const submit = async () => {
    setFormError(null);
    if (!orderId || !locationId || receipts.length === 0) return;
    try {
      await receive.mutateAsync({
        orderId,
        receipts: receipts.map((r) => ({ ...r, location: Number(locationId) })),
      });
      navigate(`/purchases/orders/${orderId}`);
    } catch (err) {
      setFormError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Could not receive stock.",
      );
    }
  };

  return (
    <div className="max-w-2xl">
      <PageHeader
        title="Receive Stock"
        description="Receive units against a placed purchase order. Each received unit is created and assigned this location, ready for sale."
      />

      <Card className="mb-4">
        <CardContent className="space-y-4 py-5">
          <div className="flex flex-col gap-1.5">
            <Label>Purchase order</Label>
            <select
              value={orderId ?? ""}
              onChange={(e) => {
                setSearchParams(e.target.value ? { order: e.target.value } : {});
                setQuantities({});
              }}
              className={selectClass}
            >
              <option value="">Select…</option>
              {receivableOrders.map((o) => (
                <option key={o.id} value={o.id}>
                  #{o.id} — {o.supplier_name} ({o.status})
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Location</Label>
            <select
              value={locationId}
              onChange={(e) => setLocationId(e.target.value)}
              className={selectClass}
            >
              <option value="">Select…</option>
              {locations.map((loc) => (
                <option key={loc.id} value={loc.id}>
                  {loc.name}
                </option>
              ))}
            </select>
          </div>
        </CardContent>
      </Card>

      {orderId && orderLoading && <p className="text-sm text-muted-foreground">Loading order…</p>}

      {order && (
        <Card className="mb-4">
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="px-4 py-2 font-medium">SKU</th>
                    <th className="px-4 py-2 font-medium">Product</th>
                    <th className="px-4 py-2 text-right font-medium">Pending</th>
                    <th className="px-4 py-2 text-right font-medium">Receive now</th>
                  </tr>
                </thead>
                <tbody>
                  {pendingLines.length === 0 && (
                    <tr>
                      <td colSpan={4} className="px-4 py-8 text-center text-muted-foreground">
                        Nothing left to receive on this order.
                      </td>
                    </tr>
                  )}
                  {pendingLines.map((line) => (
                    <tr key={line.id} className="border-b last:border-0">
                      <td className="px-4 py-2 font-mono text-xs">{line.sku}</td>
                      <td className="px-4 py-2">{line.product_name}</td>
                      <td className="px-4 py-2 text-right">{line.quantity_pending}</td>
                      <td className="px-4 py-2 text-right">
                        <input
                          type="number"
                          min={0}
                          max={line.quantity_pending}
                          value={quantities[line.id] ?? ""}
                          onChange={(e) =>
                            setQuantities((prev) => ({ ...prev, [line.id]: e.target.value }))
                          }
                          className="h-8 w-24 rounded-md border border-input bg-transparent px-2 text-right text-sm"
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {formError && <p className="mb-4 text-sm text-destructive">{formError}</p>}

      <div className="flex gap-2">
        <Button
          onClick={submit}
          disabled={receive.isPending || !orderId || !locationId || receipts.length === 0}
        >
          {receive.isPending ? "Receiving…" : `Receive ${receipts.length || 0} line(s)`}
        </Button>
        <Button type="button" variant="outline" onClick={() => navigate("/purchases/orders")}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
