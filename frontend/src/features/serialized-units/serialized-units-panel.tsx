import { useEffect, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { ApiError } from "@/api/client";
import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchSerializedUnits, serializedUnitsKey } from "./api";
import { UNIT_STATUSES } from "./types";

const PAGE_SIZE = 20;

export function SerializedUnitsPanel() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");

  // Debounce the serial-number search.
  useEffect(() => {
    const handle = setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(handle);
  }, [searchInput]);

  const query = { page, pageSize: PAGE_SIZE, search, status };
  const { data, isPending, isFetching, error, refetch } = useQuery({
    queryKey: serializedUnitsKey(query),
    queryFn: () => fetchSerializedUnits(query),
    placeholderData: keepPreviousData,
  });

  const notReady = error instanceof ApiError && [404, 501].includes(error.status);
  const units = data?.data ?? [];
  const count = data?.meta.count ?? 0;

  return (
    <div>
      <PageHeader
        title="Serial Numbers"
        description="Every physical unit, its status and location."
      />

      <div className="mb-4 flex flex-wrap gap-2">
        <Input
          placeholder="Search serial number…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          className="max-w-xs"
        />
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(1);
          }}
          className="h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        >
          <option value="">All statuses</option>
          {UNIT_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {notReady && (
        <Alert>
          <AlertTitle>Not available yet</AlertTitle>
          <AlertDescription>
            The serialized-units API ships in Phase 3. This panel is wired to the fetch client
            and will populate once that endpoint exists.
          </AlertDescription>
        </Alert>
      )}

      {error && !notReady && (
        <Alert variant="destructive">
          <AlertTitle>Couldn’t load serial numbers</AlertTitle>
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
                    <th className="px-4 py-3 font-medium">Serial</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                    <th className="px-4 py-3 font-medium">Location</th>
                    <th className="px-4 py-3 font-medium">SKU</th>
                    <th className="px-4 py-3 font-medium">Product</th>
                  </tr>
                </thead>
                <tbody>
                  {isPending &&
                    Array.from({ length: 6 }).map((_, i) => (
                      <tr key={i} className="border-b">
                        {Array.from({ length: 5 }).map((__, j) => (
                          <td key={j} className="px-4 py-3">
                            <Skeleton className="h-4 w-24" />
                          </td>
                        ))}
                      </tr>
                    ))}

                  {!isPending && units.length === 0 && (
                    <tr>
                      <td
                        colSpan={5}
                        className="px-4 py-12 text-center text-sm text-muted-foreground"
                      >
                        No serialized units{search || status ? " match these filters" : " yet"}.
                      </td>
                    </tr>
                  )}

                  {units.map((unit) => (
                    <tr key={unit.id} className="border-b last:border-0">
                      <td className="px-4 py-3 font-mono">{unit.serial_number}</td>
                      <td className="px-4 py-3">{unit.status}</td>
                      <td className="px-4 py-3">{unit.location ?? "—"}</td>
                      <td className="px-4 py-3">{unit.sku ?? "—"}</td>
                      <td className="px-4 py-3">{unit.product ?? "—"}</td>
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
            {count} unit{count === 1 ? "" : "s"}
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
