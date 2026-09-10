import { useState } from "react";
import { Link } from "react-router-dom";
import { Plus } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useStockTransfers } from "./hooks";
import { transferStatusVariant } from "./status";

const selectClass =
  "h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

export function StockTransfersPage() {
  const [status, setStatus] = useState("");
  const { data, isPending, error, refetch } = useStockTransfers(
    status ? { status } : {},
  );
  const transfers = data?.data ?? [];

  return (
    <div>
      <PageHeader
        title="Stock Transfers"
        description="Scan-based movement of serialized units between locations."
        actions={
          <Button asChild size="sm">
            <Link to="/inventory/transfers/new">
              <Plus className="size-4" /> New transfer
            </Link>
          </Button>
        }
      />

      <div className="mb-4">
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className={selectClass}
        >
          <option value="">All statuses</option>
          <option value="OPEN">Open</option>
          <option value="COMPLETED">Completed</option>
          <option value="CANCELLED">Cancelled</option>
        </select>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertTitle>Couldn&apos;t load transfers</AlertTitle>
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
                    <th className="px-4 py-3 font-medium">#</th>
                    <th className="px-4 py-3 font-medium">Route</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                    <th className="px-4 py-3 text-right font-medium">Units</th>
                    <th className="px-4 py-3 font-medium">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {isPending &&
                    Array.from({ length: 5 }).map((_, i) => (
                      <tr key={i} className="border-b">
                        {Array.from({ length: 5 }).map((__, j) => (
                          <td key={j} className="px-4 py-3">
                            <Skeleton className="h-4 w-20" />
                          </td>
                        ))}
                      </tr>
                    ))}

                  {!isPending && transfers.length === 0 && (
                    <tr>
                      <td
                        colSpan={5}
                        className="px-4 py-12 text-center text-sm text-muted-foreground"
                      >
                        No transfers{status ? " with this status" : " yet"}.
                      </td>
                    </tr>
                  )}

                  {transfers.map((transfer) => (
                    <tr key={transfer.id} className="border-b last:border-0 hover:bg-muted/50">
                      <td className="px-4 py-3">
                        <Link
                          to={`/inventory/transfers/${transfer.id}`}
                          className="text-primary underline-offset-4 hover:underline"
                        >
                          {transfer.id}
                        </Link>
                      </td>
                      <td className="px-4 py-3">
                        {transfer.from_location_name} → {transfer.to_location_name}
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant={transferStatusVariant(transfer.status)}>
                          {transfer.status}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-right">{transfer.line_count}</td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {new Date(transfer.created_at).toLocaleDateString()}
                      </td>
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
