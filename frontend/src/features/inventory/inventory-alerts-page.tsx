import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useInventoryAlerts } from "./hooks";
import { ALERT_LABELS, alertVariant } from "./status";
import type { InventoryAlert } from "./types";

function describe(alert: InventoryAlert): string {
  switch (alert.type) {
    case "out_of_stock":
      return "No stock available.";
    case "low_stock":
      return `${alert.available} available, at or below the minimum of ${alert.min_quantity}.`;
    case "overstock":
      return `${alert.available} available, at or above the maximum of ${alert.max_quantity}.`;
    case "balance_mismatch":
      return `Cache shows ${alert.cached} ${alert.status}, live count is ${alert.expected}.`;
    default:
      return "";
  }
}

export function InventoryAlertsPage() {
  const { data: alerts, isPending, error, refetch } = useInventoryAlerts();

  return (
    <div>
      <PageHeader
        title="Inventory Alerts"
        description="Low-stock, out-of-stock and overstock against your stock-level policies, plus cache drift."
      />

      {error && (
        <Alert variant="destructive">
          <AlertTitle>Couldn&apos;t load alerts</AlertTitle>
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
                    <th className="px-4 py-3 font-medium">Alert</th>
                    <th className="px-4 py-3 font-medium">SKU</th>
                    <th className="px-4 py-3 font-medium">Location</th>
                    <th className="px-4 py-3 font-medium">Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {isPending &&
                    Array.from({ length: 4 }).map((_, i) => (
                      <tr key={i} className="border-b">
                        {Array.from({ length: 4 }).map((__, j) => (
                          <td key={j} className="px-4 py-3">
                            <Skeleton className="h-4 w-24" />
                          </td>
                        ))}
                      </tr>
                    ))}

                  {!isPending && (alerts?.length ?? 0) === 0 && (
                    <tr>
                      <td
                        colSpan={4}
                        className="px-4 py-12 text-center text-sm text-muted-foreground"
                      >
                        No active alerts. Stock is within every policy.
                      </td>
                    </tr>
                  )}

                  {alerts?.map((alert, i) => (
                    <tr key={i} className="border-b last:border-0">
                      <td className="px-4 py-3">
                        <Badge variant={alertVariant(alert.type)}>{ALERT_LABELS[alert.type]}</Badge>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs">
                        {alert.variant.sku}
                        <div className="text-muted-foreground">{alert.variant.product_name}</div>
                      </td>
                      <td className="px-4 py-3">{alert.location?.name ?? "All locations"}</td>
                      <td className="px-4 py-3 text-muted-foreground">{describe(alert)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
