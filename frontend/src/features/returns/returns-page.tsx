import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Plus } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useReturns } from "./hooks";

const PAGE_SIZE = 20;

export function ReturnsPage() {
  const [page, setPage] = useState(1);
  const query = useMemo(() => ({ page, page_size: PAGE_SIZE }), [page]);
  const { data, isPending, isFetching, error, refetch } = useReturns(query);
  const returns = data?.data ?? [];
  const count = data?.meta.count ?? 0;

  return (
    <div>
      <PageHeader
        title="Returns"
        description="Units handed back by a customer, refunded, and awaiting inspection."
        actions={
          <Button asChild>
            <Link to="/sales/returns/new">
              <Plus className="mr-1 size-4" />
              New return
            </Link>
          </Button>
        }
      />

      {error && (
        <Alert variant="destructive">
          <AlertTitle>Couldn&apos;t load returns</AlertTitle>
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
                    <th className="px-4 py-3 font-medium">Return #</th>
                    <th className="px-4 py-3 font-medium">Sale</th>
                    <th className="px-4 py-3 font-medium">Reason</th>
                    <th className="px-4 py-3 text-right font-medium">Units</th>
                    <th className="px-4 py-3 text-right font-medium">Refund</th>
                    <th className="px-4 py-3 font-medium">Inspection</th>
                    <th className="px-4 py-3 font-medium">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {isPending &&
                    Array.from({ length: 8 }).map((_, i) => (
                      <tr key={i} className="border-b">
                        {Array.from({ length: 7 }).map((__, j) => (
                          <td key={j} className="px-4 py-3">
                            <Skeleton className="h-4 w-16" />
                          </td>
                        ))}
                      </tr>
                    ))}

                  {!isPending && returns.length === 0 && (
                    <tr>
                      <td colSpan={7} className="px-4 py-12 text-center text-sm text-muted-foreground">
                        No returns yet — start one from a sold unit&apos;s serial.
                      </td>
                    </tr>
                  )}

                  {returns.map((ret) => (
                    <tr key={ret.id} className="border-b last:border-0">
                      <td className="px-4 py-3 font-mono text-xs">
                        <Link to={`/sales/returns/${ret.id}`} className="hover:underline">
                          #{ret.id}
                        </Link>
                      </td>
                      <td className="px-4 py-3">#{ret.sale}</td>
                      <td className="px-4 py-3">{ret.reason}</td>
                      <td className="px-4 py-3 text-right">{ret.unit_count}</td>
                      <td className="px-4 py-3 text-right font-medium">
                        ₹{Number(ret.refund_total).toLocaleString("en-IN")}
                      </td>
                      <td className="px-4 py-3">
                        {ret.pending_count > 0 ? (
                          <Badge variant="secondary">
                            {ret.pending_count} pending
                          </Badge>
                        ) : (
                          <Badge variant="default">Complete</Badge>
                        )}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">
                        {new Date(ret.created_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {!error && count > PAGE_SIZE && (
        <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground">
          <span>
            {count} return{count === 1 ? "" : "s"}
            {isFetching ? " · updating…" : ""}
          </span>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={!data?.meta.previous}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Previous
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!data?.meta.next}
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
