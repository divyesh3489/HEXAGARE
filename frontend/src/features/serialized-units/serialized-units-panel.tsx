import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useDebounced, useLocations, useSerializedUnits } from "./hooks";
import { statusBadgeVariant } from "./status";
import { UNIT_STATUSES } from "./types";

const PAGE_SIZE = 20;

const selectClass =
  "h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

export function SerializedUnitsPanel() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [location, setLocation] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const search = useDebounced(searchInput.trim());

  const { data: locationsData } = useLocations();
  const locations = locationsData?.data ?? [];

  const query = useMemo(
    () => ({
      page,
      page_size: PAGE_SIZE,
      search: search || undefined,
      status: status || undefined,
      location: location ? Number(location) : undefined,
    }),
    [page, search, status, location],
  );

  const { data, isPending, isFetching, error, refetch } = useSerializedUnits(query);

  const units = data?.data ?? [];
  const count = data?.meta.count ?? 0;

  const resetPage = () => setPage(1);

  return (
    <div>
      <PageHeader
        title="Product Units"
        description="Every physical unit — its serial number, status and location."
      />

      <div className="mb-4 flex flex-wrap gap-2">
        <Input
          placeholder="Search serial number…"
          value={searchInput}
          onChange={(e) => {
            setSearchInput(e.target.value);
            resetPage();
          }}
          className="max-w-xs"
        />
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            resetPage();
          }}
          className={selectClass}
        >
          <option value="">All statuses</option>
          {UNIT_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          value={location}
          onChange={(e) => {
            setLocation(e.target.value);
            resetPage();
          }}
          className={selectClass}
        >
          <option value="">All locations</option>
          {locations.map((loc) => (
            <option key={loc.id} value={loc.id}>
              {loc.name}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertTitle>Couldn’t load product units</AlertTitle>
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
                        No product units
                        {search || status || location ? " match these filters" : " yet"}.
                      </td>
                    </tr>
                  )}

                  {units.map((unit) => (
                    <tr
                      key={unit.id}
                      className="border-b transition-colors last:border-0 hover:bg-muted/50"
                    >
                      <td className="px-4 py-3 font-mono">
                        <Link
                          to={`/products/units/${unit.id}`}
                          className="text-primary underline-offset-4 hover:underline"
                        >
                          {unit.serial_number}
                        </Link>
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant={statusBadgeVariant(unit.status)}>{unit.status}</Badge>
                      </td>
                      <td className="px-4 py-3">{unit.location_name}</td>
                      <td className="px-4 py-3 font-mono text-xs">{unit.sku}</td>
                      <td className="px-4 py-3">{unit.product_name}</td>
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
