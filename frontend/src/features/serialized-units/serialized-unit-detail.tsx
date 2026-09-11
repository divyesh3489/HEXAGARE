import type { ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useUnitProfit } from "@/features/finance/hooks";
import { useHasPermission } from "@/hooks/use-auth";
import { useSerializedUnit, useUnitBarcode } from "./hooks";
import { statusBadgeVariant } from "./status";
import type { SerializedUnitDetail } from "./types";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 border-b py-2 text-sm last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{children}</span>
    </div>
  );
}

function money(value: string | null): string {
  if (value === null) return "—";
  const n = Number(value);
  return Number.isNaN(n) ? value : `₹${n.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
}

export function SerializedUnitDetailPage() {
  const params = useParams();
  const navigate = useNavigate();
  const unitId = Number(params.unitId);
  const { data: unit, isPending, error } = useSerializedUnit(
    Number.isNaN(unitId) ? undefined : unitId,
  );

  if (isPending) {
    return (
      <div>
        <PageHeader title="Product Unit" />
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      </div>
    );
  }

  if (error || !unit) {
    return (
      <div>
        <PageHeader title="Product Unit" />
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            This product unit could not be loaded.
            <div className="mt-3">
              <Button variant="outline" size="sm" onClick={() => navigate("/products/units")}>
                Back to units
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={unit.serial_number}
        description="Serialized unit — full chain, pricing and history."
        actions={
          <Button variant="outline" size="sm" onClick={() => navigate("/products/units")}>
            Back to units
          </Button>
        }
      />

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Chain</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <Row label="Status">
              <Badge variant={statusBadgeVariant(unit.status)}>{unit.status}</Badge>
            </Row>
            <Row label="Serial number">
              <span className="font-mono">{unit.serial_number}</span>
            </Row>
            <Row label="Location">{unit.location_name}</Row>
            <Row label="Product">
              <Link
                to={`/products/${unit.product.id}`}
                className="text-primary underline-offset-4 hover:underline"
              >
                {unit.product.name}
              </Link>
            </Row>
            <Row label="Category">{unit.product.category_name}</Row>
            <Row label="Variant">{unit.variant.name || "—"}</Row>
            <Row label="SKU">
              <span className="font-mono text-xs">{unit.variant.sku}</span>
            </Row>
            <Row label="Purchase cost">{money(unit.purchase_cost)}</Row>
          </CardContent>
        </Card>

        <div className="space-y-6">
          <PricingCard unit={unit} />
          <BarcodeCard unitId={unit.id} serial={unit.serial_number} />
        </div>
      </div>

      <ProfitCard unit={unit} />
      <HistoryCard unit={unit} />
    </div>
  );
}

function PricingCard({ unit }: { unit: SerializedUnitDetail }) {
  const p = unit.pricing;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Pricing &amp; GST</CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <Row label="Selling price (incl. GST)">{money(p.effective_selling_price)}</Row>
        <Row label="Taxable value">{money(p.base_price)}</Row>
        <Row label={`GST (${Number(p.effective_tax_rate)}%)`}>{money(p.gst_amount)}</Row>
        <Row label="— CGST / SGST">
          {money(p.cgst_amount)} / {money(p.sgst_amount)}
        </Row>
        <Row label="MRP">{money(p.effective_mrp)}</Row>
        <Row label="Discount">
          {money(p.discount_amount)} ({Number(p.discount_percent)}%)
        </Row>
      </CardContent>
    </Card>
  );
}

function BarcodeCard({ unitId, serial }: { unitId: number; serial: string }) {
  const { objectUrl, isPending, error } = useUnitBarcode(unitId);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Barcode</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col items-center gap-2 pt-0">
        {isPending && <Skeleton className="h-20 w-full" />}
        {error && (
          <Alert variant="destructive">
            <AlertTitle>Couldn’t render the barcode</AlertTitle>
            <AlertDescription>
              {error instanceof Error ? error.message : "Unknown error."}
            </AlertDescription>
          </Alert>
        )}
        {objectUrl && (
          <img
            src={objectUrl}
            alt={`Code128 barcode for ${serial}`}
            className="max-w-full"
          />
        )}
        <p className="text-xs text-muted-foreground">
          Code128 · rendered on demand, never stored.
        </p>
      </CardContent>
    </Card>
  );
}

const SOLD_STATUSES = new Set(["SOLD", "RETURNED"]);

function ProfitCard({ unit }: { unit: SerializedUnitDetail }) {
  const canViewFinance = useHasPermission()("finance.view");
  const eligible = canViewFinance && SOLD_STATUSES.has(unit.status);
  const { data: profit, isPending, error } = useUnitProfit(unit.id, eligible);

  if (!eligible) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Profit (this sale)</CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        {isPending && <Skeleton className="h-32 w-full" />}
        {error && (
          <p className="text-sm text-muted-foreground">Profit could not be computed for this unit.</p>
        )}
        {profit && (
          <>
            <Row label="Purchase cost">{money(profit.purchase_cost)}</Row>
            <Row label="Taxable selling value">{money(profit.taxable_selling_value)}</Row>
            <Row label="Amazon fees">{money(profit.amazon_fees)}</Row>
            <Row label="Courier">{money(profit.courier)}</Row>
            <Row label="Advertising">{money(profit.advertising)}</Row>
            <Row label="Other charges">{money(profit.other_charges)}</Row>
            <Row label="Unit profit">
              <span className="font-semibold">{money(profit.unit_profit)}</span>
            </Row>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function HistoryCard({ unit }: { unit: SerializedUnitDetail }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>History</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-6 py-3 font-medium">When</th>
                <th className="px-6 py-3 font-medium">Change</th>
                <th className="px-6 py-3 font-medium">Location</th>
                <th className="px-6 py-3 font-medium">Note</th>
                <th className="px-6 py-3 font-medium">By</th>
              </tr>
            </thead>
            <tbody>
              {unit.events.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-muted-foreground">
                    No history recorded.
                  </td>
                </tr>
              )}
              {unit.events.map((ev) => (
                <tr key={ev.id} className="border-b last:border-0">
                  <td className="px-6 py-3 whitespace-nowrap">
                    {new Date(ev.created_at).toLocaleString()}
                  </td>
                  <td className="px-6 py-3 font-mono text-xs">
                    {(ev.from_status || "—") + " → " + ev.to_status}
                  </td>
                  <td className="px-6 py-3">{ev.location_name ?? "—"}</td>
                  <td className="px-6 py-3">{ev.note || "—"}</td>
                  <td className="px-6 py-3">{ev.actor_email ?? "system"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
