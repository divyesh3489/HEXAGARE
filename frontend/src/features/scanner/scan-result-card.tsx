import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { PackageSearch, RefreshCw, ScanLine } from "lucide-react";

import { ApiError } from "@/api/client";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { statusBadgeVariant } from "@/features/serialized-units/status";
import type { SerializedUnitDetail } from "@/features/serialized-units/types";

function money(value: string | null): string {
  if (value === null) return "—";
  const n = Number(value);
  return Number.isNaN(n)
    ? value
    : `₹${n.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 border-b py-2 text-sm last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{children}</span>
    </div>
  );
}

function Shell({ code, children }: { code: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <ScanLine className="size-4 text-muted-foreground" />
          <span className="font-mono">{code}</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">{children}</CardContent>
    </Card>
  );
}

interface ScanResultCardProps {
  code: string;
  isPending: boolean;
  error: unknown;
  unit: SerializedUnitDetail | undefined;
  onScanAnother: () => void;
  onRetry: () => void;
}

export function ScanResultCard({
  code,
  isPending,
  error,
  unit,
  onScanAnother,
  onRetry,
}: ScanResultCardProps) {
  const scanAnother = (
    <Button className="mt-4 w-full" onClick={onScanAnother}>
      <ScanLine /> Scan another
    </Button>
  );

  if (isPending) {
    return (
      <Shell code={code}>
        <div className="space-y-2 py-1">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-6 w-full" />
          ))}
        </div>
      </Shell>
    );
  }

  if (error) {
    const status = error instanceof ApiError ? error.status : undefined;

    if (status === 404) {
      return (
        <Shell code={code}>
          <div className="flex flex-col items-center gap-2 py-6 text-center">
            <PackageSearch className="size-8 text-muted-foreground" />
            <p className="text-sm font-medium">No unit matches this code</p>
            <p className="text-xs text-muted-foreground">
              It may be from another system, or the label is damaged.
            </p>
          </div>
          {scanAnother}
        </Shell>
      );
    }

    const title =
      status === 403
        ? "You can't look up units"
        : status === 401
          ? "Your session has expired"
          : "Lookup failed";
    const description =
      status === 403
        ? "Your role is missing the barcode.scan permission."
        : error instanceof Error
          ? error.message
          : "Something went wrong resolving that code.";

    return (
      <Shell code={code}>
        <Alert variant="destructive">
          <AlertTitle>{title}</AlertTitle>
          <AlertDescription>{description}</AlertDescription>
        </Alert>
        <div className="mt-4 flex gap-2">
          {status !== 403 && status !== 401 && (
            <Button variant="outline" className="flex-1" onClick={onRetry}>
              <RefreshCw /> Retry
            </Button>
          )}
          <Button className="flex-1" onClick={onScanAnother}>
            <ScanLine /> Scan another
          </Button>
        </div>
      </Shell>
    );
  }

  if (!unit) return null;

  return (
    <Shell code={code}>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm text-muted-foreground">Status</span>
        <Badge variant={statusBadgeVariant(unit.status)}>{unit.status}</Badge>
      </div>
      <Row label="Product">{unit.product.name}</Row>
      <Row label="Category">{unit.product.category_name}</Row>
      <Row label="Variant">{unit.variant.name || "—"}</Row>
      <Row label="SKU">
        <span className="font-mono text-xs">{unit.variant.sku}</span>
      </Row>
      <Row label="Price (incl. GST)">{money(unit.pricing.effective_selling_price)}</Row>
      <Row label={`GST (${Number(unit.pricing.effective_tax_rate)}%)`}>
        {money(unit.pricing.gst_amount)}
      </Row>
      <Row label="MRP">{money(unit.pricing.effective_mrp)}</Row>
      <Row label="Location">{unit.location_name}</Row>

      <div className="mt-4 flex gap-2">
        <Button variant="outline" className="flex-1" asChild>
          <Link to={`/products/units/${unit.id}`}>Open full detail</Link>
        </Button>
        <Button className="flex-1" onClick={onScanAnother}>
          <ScanLine /> Scan another
        </Button>
      </div>
    </Shell>
  );
}
