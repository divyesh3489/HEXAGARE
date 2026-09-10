import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "@/api/client";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { useInventoryLocations, useTransferMutations } from "./hooks";

const selectClass =
  "h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

export function StockTransferNewPage() {
  const navigate = useNavigate();
  const { data: locationsData } = useInventoryLocations();
  const locations = (locationsData?.data ?? []).filter((l) => l.is_active);
  const { create } = useTransferMutations();

  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [note, setNote] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    create.mutate(
      { from_location: Number(from), to_location: Number(to), note: note || undefined },
      { onSuccess: (transfer) => navigate(`/inventory/transfers/${transfer.id}`) },
    );
  };

  const error = create.error;
  const fieldError = (name: string) =>
    error instanceof ApiError ? error.fieldError(name) : undefined;

  return (
    <div className="max-w-lg">
      <PageHeader title="New Stock Transfer" description="Pick the route, then scan units onto it." />

      <Card>
        <CardContent className="pt-6">
          <form onSubmit={submit} className="flex flex-col gap-4">
            <div>
              <Label htmlFor="from">From location</Label>
              <select
                id="from"
                value={from}
                onChange={(e) => setFrom(e.target.value)}
                required
                className={selectClass}
              >
                <option value="">Select…</option>
                {locations.map((loc) => (
                  <option key={loc.id} value={loc.id}>
                    {loc.name}
                  </option>
                ))}
              </select>
              {fieldError("from_location") && (
                <p className="mt-1 text-xs text-destructive">{fieldError("from_location")}</p>
              )}
            </div>

            <div>
              <Label htmlFor="to">To location</Label>
              <select
                id="to"
                value={to}
                onChange={(e) => setTo(e.target.value)}
                required
                className={selectClass}
              >
                <option value="">Select…</option>
                {locations
                  .filter((loc) => String(loc.id) !== from)
                  .map((loc) => (
                    <option key={loc.id} value={loc.id}>
                      {loc.name}
                    </option>
                  ))}
              </select>
              {fieldError("to_location") && (
                <p className="mt-1 text-xs text-destructive">{fieldError("to_location")}</p>
              )}
            </div>

            <div>
              <Label htmlFor="note">Note (optional)</Label>
              <input
                id="note"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                className={selectClass}
                placeholder="e.g. weekly Amazon restock"
              />
            </div>

            {error && !fieldError("from_location") && !fieldError("to_location") && (
              <p className="text-sm text-destructive">
                {error instanceof ApiError
                  ? error.detail
                  : error instanceof Error
                    ? error.message
                    : "Couldn't create the transfer."}
              </p>
            )}

            <div className="flex gap-2">
              <Button type="submit" disabled={create.isPending || !from || !to}>
                {create.isPending ? "Creating…" : "Create transfer"}
              </Button>
              <Button type="button" variant="outline" onClick={() => navigate("/inventory/transfers")}>
                Cancel
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
