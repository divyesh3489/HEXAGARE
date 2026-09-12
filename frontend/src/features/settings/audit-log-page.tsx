import { useMemo, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuditLog } from "./hooks";
import type { AuditLogEntry } from "./types";

const PAGE_SIZE = 30;

function actionLabel(action: string): string {
  return action
    .split(".")
    .join(" ")
    .replace(/^\w/, (c) => c.toUpperCase());
}

function changesSummary(entry: AuditLogEntry): string {
  const keys = Object.keys(entry.changes ?? {});
  if (keys.length === 0) return "—";
  return keys
    .slice(0, 3)
    .map((k) => `${k}: ${String(entry.changes[k].old)} → ${String(entry.changes[k].new)}`)
    .join("; ");
}

export function AuditLogPage() {
  const [page, setPage] = useState(1);
  const [action, setAction] = useState("");
  const [objectType, setObjectType] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const query = useMemo(
    () => ({
      page,
      page_size: PAGE_SIZE,
      action: action || undefined,
      object_type: objectType || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
    }),
    [page, action, objectType, dateFrom, dateTo],
  );
  const { data, isPending, isFetching, error } = useAuditLog(query);

  const entries = data?.data ?? [];
  const count = data?.meta.count ?? 0;

  return (
    <div>
      <PageHeader
        title="Activity Log"
        description="Every tracked business action -- products, stock, orders, invoices, purchases, expenses, users and settings."
      />

      <div className="mb-4 flex flex-wrap gap-3">
        <Input
          placeholder="Action, e.g. order.created"
          value={action}
          onChange={(e) => {
            setAction(e.target.value);
            setPage(1);
          }}
          className="w-56"
        />
        <Input
          placeholder="Object type, e.g. sale"
          value={objectType}
          onChange={(e) => {
            setObjectType(e.target.value);
            setPage(1);
          }}
          className="w-48"
        />
        <Input
          type="date"
          value={dateFrom}
          onChange={(e) => {
            setDateFrom(e.target.value);
            setPage(1);
          }}
          className="w-auto"
        />
        <Input
          type="date"
          value={dateTo}
          onChange={(e) => {
            setDateTo(e.target.value);
            setPage(1);
          }}
          className="w-auto"
        />
      </div>

      {error && <p className="text-sm text-destructive">Couldn’t load the activity log.</p>}

      {!error && (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="px-4 py-3 font-medium">When</th>
                    <th className="px-4 py-3 font-medium">Actor</th>
                    <th className="px-4 py-3 font-medium">Action</th>
                    <th className="px-4 py-3 font-medium">Object</th>
                    <th className="px-4 py-3 font-medium">Changes</th>
                  </tr>
                </thead>
                <tbody>
                  {isPending && (
                    <tr>
                      <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                        Loading…
                      </td>
                    </tr>
                  )}
                  {!isPending && entries.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-4 py-12 text-center text-muted-foreground">
                        No activity matches these filters.
                      </td>
                    </tr>
                  )}
                  {entries.map((entry) => (
                    <tr key={entry.id} className="border-b last:border-0 align-top">
                      <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">
                        {new Date(entry.created_at).toLocaleString()}
                      </td>
                      <td className="px-4 py-3">{entry.actor_email ?? "System"}</td>
                      <td className="px-4 py-3">{actionLabel(entry.action)}</td>
                      <td className="px-4 py-3">
                        <div>{entry.object_repr || "—"}</div>
                        {entry.object_type && (
                          <div className="text-xs text-muted-foreground">
                            {entry.object_type} #{entry.object_id}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">
                        {changesSummary(entry)}
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
            {count} entr{count === 1 ? "y" : "ies"}
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
