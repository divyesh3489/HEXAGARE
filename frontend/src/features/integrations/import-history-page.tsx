import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useImportBatch, useImportBatches } from "./hooks";
import { importBatchStatusVariant } from "./status";
import type { ImportBatchListItem } from "./types";

const PAGE_SIZE = 20;

export function AmazonImportHistoryPage() {
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<number | null>(null);
  const query = useMemo(() => ({ page, page_size: PAGE_SIZE }), [page]);
  const { data, isPending, error, refetch } = useImportBatches(query);
  const batches = data?.data ?? [];
  const count = data?.meta.count ?? 0;

  return (
    <div>
      <PageHeader
        title="Amazon import history"
        description="Every CSV upload and how it went."
        actions={
          <Button asChild>
            <Link to="/integrations/amazon/import">Upload a CSV</Link>
          </Button>
        }
      />

      {error && (
        <Alert variant="destructive">
          <AlertTitle>Couldn&apos;t load import history</AlertTitle>
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
                    <th className="px-4 py-3 font-medium">Batch</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                    <th className="px-4 py-3 text-right font-medium">Rows</th>
                    <th className="px-4 py-3 text-right font-medium">Created</th>
                    <th className="px-4 py-3 text-right font-medium">Updated</th>
                    <th className="px-4 py-3 text-right font-medium">Failed</th>
                    <th className="px-4 py-3 font-medium">By</th>
                    <th className="px-4 py-3 font-medium">When</th>
                  </tr>
                </thead>
                <tbody>
                  {isPending &&
                    Array.from({ length: 6 }).map((_, i) => (
                      <tr key={i} className="border-b">
                        {Array.from({ length: 8 }).map((__, j) => (
                          <td key={j} className="px-4 py-3">
                            <Skeleton className="h-4 w-full" />
                          </td>
                        ))}
                      </tr>
                    ))}
                  {!isPending && batches.length === 0 && (
                    <tr>
                      <td colSpan={8} className="px-4 py-12 text-center text-muted-foreground">
                        No imports yet.
                      </td>
                    </tr>
                  )}
                  {batches.map((batch) => (
                    <BatchRow
                      key={batch.id}
                      batch={batch}
                      expanded={expanded === batch.id}
                      onToggle={() => setExpanded(expanded === batch.id ? null : batch.id)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {count > PAGE_SIZE && (
        <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground">
          <span>
            Page {page} of {Math.ceil(count / PAGE_SIZE)}
          </span>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Previous
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={page >= Math.ceil(count / PAGE_SIZE)}
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

function BatchRow({
  batch,
  expanded,
  onToggle,
}: {
  batch: ImportBatchListItem;
  expanded: boolean;
  onToggle: () => void;
}) {
  // The list already carries status/counts; only fetch the detail (for
  // error_log) once a row is expanded.
  const detail = useImportBatch(expanded ? batch.id : undefined);
  const errorLog = detail.data?.error_log;

  return (
    <>
      <tr className="cursor-pointer border-b last:border-0 hover:bg-muted/40" onClick={onToggle}>
        <td className="px-4 py-3 font-medium">#{batch.id}</td>
        <td className="px-4 py-3">
          <Badge variant={importBatchStatusVariant(batch.status)}>{batch.status}</Badge>
        </td>
        <td className="px-4 py-3 text-right">{batch.total_rows}</td>
        <td className="px-4 py-3 text-right">{batch.orders_created}</td>
        <td className="px-4 py-3 text-right">{batch.orders_updated}</td>
        <td className="px-4 py-3 text-right">{batch.orders_failed}</td>
        <td className="px-4 py-3 text-muted-foreground">{batch.created_by_email ?? "—"}</td>
        <td className="px-4 py-3 text-muted-foreground">
          {new Date(batch.created_at).toLocaleString()}
        </td>
      </tr>
      {expanded && errorLog === undefined && (
        <tr className="border-b bg-muted/20 last:border-0">
          <td colSpan={8} className="px-4 py-3">
            <Skeleton className="h-4 w-full" />
          </td>
        </tr>
      )}
      {expanded && errorLog && errorLog.length > 0 && (
        <tr className="border-b bg-muted/20 last:border-0">
          <td colSpan={8} className="px-4 py-3">
            <div className="space-y-1 text-xs">
              {errorLog.map((entry, i) => (
                <div key={i} className="flex gap-2">
                  <span className="font-mono text-muted-foreground">
                    {entry.order_id ?? `row ${entry.row}`}
                  </span>
                  <span>{entry.message}</span>
                </div>
              ))}
            </div>
          </td>
        </tr>
      )}
      {expanded && errorLog && errorLog.length === 0 && (
        <tr className="border-b bg-muted/20 last:border-0">
          <td colSpan={8} className="px-4 py-3 text-xs text-muted-foreground">
            No errors.
          </td>
        </tr>
      )}
    </>
  );
}
