import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useInventoryAlerts, useInventoryLocations, useInventoryOverview } from "./hooks";
import { ALERT_LABELS, alertVariant, stockStatusVariant } from "./status";
import { STOCK_STATUSES, type OverviewRow } from "./types";

const selectClass =
  "h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

function pivot(rows: OverviewRow[]) {
  const byKey = new Map<
    string,
    { sku: string; product_name: string; location_name: string; buckets: Record<string, number> }
  >();
  for (const row of rows) {
    const key = `${row.variant}:${row.location}`;
    const entry =
      byKey.get(key) ??
      {
        sku: row.sku,
        product_name: row.product_name,
        location_name: row.location_name,
        buckets: {},
      };
    entry.buckets[row.status] = (entry.buckets[row.status] ?? 0) + row.quantity;
    byKey.set(key, entry);
  }
  return [...byKey.values()].sort(
    (a, b) => a.sku.localeCompare(b.sku) || a.location_name.localeCompare(b.location_name),
  );
}

export function InventoryOverviewPage() {
  const [location, setLocation] = useState("");
  const { data: locationsData } = useInventoryLocations();
  const locations = locationsData?.data ?? [];

  const query = useMemo(
    () => (location ? { location: Number(location) } : {}),
    [location],
  );
  const { data, isPending, isFetching, error, refetch } = useInventoryOverview(query);
  const { data: alerts } = useInventoryAlerts(query);

  const rows = data ? pivot(data.rows) : [];
  const activeStatuses = STOCK_STATUSES.filter((s) => (data?.totals_by_status?.[s] ?? 0) > 0);
  const columns = activeStatuses.length ? activeStatuses : (["AVAILABLE"] as const);

  return (
    <div>
      <PageHeader
        title="Inventory Overview"
        description="Stock by status and location, counted live from the serialized units."
        actions={
          <select
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            className={selectClass}
          >
            <option value="">All locations</option>
            {locations.map((loc) => (
              <option key={loc.id} value={loc.id}>
                {loc.name}
              </option>
            ))}
          </select>
        }
      />

      {data && !data.cache_matches && (
        <Alert className="mb-4">
          <AlertTriangle className="size-4" />
          <AlertTitle>Balance cache is behind the live counts</AlertTitle>
          <AlertDescription>
            A unit was moved through the status-only endpoint, which doesn&apos;t touch the ledger.
            The figures below are the live truth; run{" "}
            <code className="rounded bg-muted px-1">manage.py rebuild_inventory_balances</code> to
            resync the cache used by alerts and reports.
          </AlertDescription>
        </Alert>
      )}

      {alerts && alerts.length > 0 && (
        <Card className="mb-4">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">
              {alerts.length} active alert{alerts.length === 1 ? "" : "s"}{" "}
              <Link to="/inventory/alerts" className="text-primary hover:underline">
                view all
              </Link>
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {alerts.slice(0, 8).map((a, i) => (
              <Badge key={i} variant={alertVariant(a.type)}>
                {a.variant.sku}: {ALERT_LABELS[a.type]}
              </Badge>
            ))}
          </CardContent>
        </Card>
      )}

      {error && (
        <Alert variant="destructive">
          <AlertTitle>Couldn&apos;t load the overview</AlertTitle>
          <AlertDescription className="flex flex-col items-start gap-2">
            <span>{error instanceof Error ? error.message : "Unknown error."}</span>
            <Button size="sm" variant="outline" onClick={() => refetch()}>
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {!error && (
        <>
          <div className="mb-4 flex flex-wrap gap-2">
            {columns.map((status) => (
              <div
                key={status}
                className="rounded-md border px-3 py-2 text-sm"
              >
                <div className="text-xs uppercase tracking-wider text-muted-foreground">
                  {status}
                </div>
                <div className="text-lg font-semibold">
                  {data?.totals_by_status?.[status] ?? 0}
                </div>
              </div>
            ))}
          </div>

          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                      <th className="px-4 py-3 font-medium">SKU</th>
                      <th className="px-4 py-3 font-medium">Location</th>
                      {columns.map((status) => (
                        <th key={status} className="px-4 py-3 text-right font-medium">
                          {status}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {isPending &&
                      Array.from({ length: 5 }).map((_, i) => (
                        <tr key={i} className="border-b">
                          {Array.from({ length: columns.length + 2 }).map((__, j) => (
                            <td key={j} className="px-4 py-3">
                              <Skeleton className="h-4 w-16" />
                            </td>
                          ))}
                        </tr>
                      ))}

                    {!isPending && rows.length === 0 && (
                      <tr>
                        <td
                          colSpan={columns.length + 2}
                          className="px-4 py-12 text-center text-sm text-muted-foreground"
                        >
                          No stock recorded yet.
                        </td>
                      </tr>
                    )}

                    {rows.map((row) => (
                      <tr key={`${row.sku}:${row.location_name}`} className="border-b last:border-0">
                        <td className="px-4 py-3 font-mono text-xs">
                          {row.sku}
                          <div className="text-muted-foreground">{row.product_name}</div>
                        </td>
                        <td className="px-4 py-3">{row.location_name}</td>
                        {columns.map((status) => {
                          const qty = row.buckets[status] ?? 0;
                          return (
                            <td key={status} className="px-4 py-3 text-right">
                              {qty > 0 ? (
                                <Badge variant={stockStatusVariant(status)}>{qty}</Badge>
                              ) : (
                                <span className="text-muted-foreground">—</span>
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
          {isFetching && (
            <p className="mt-3 text-sm text-muted-foreground">Updating…</p>
          )}
        </>
      )}
    </div>
  );
}
