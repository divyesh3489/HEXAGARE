import { useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useStockTransfer, useTransferMutations } from "./hooks";
import { stockStatusVariant, transferStatusVariant } from "./status";

export function StockTransferDetailPage() {
  const params = useParams();
  const navigate = useNavigate();
  const transferId = Number(params.transferId);
  const valid = !Number.isNaN(transferId);

  const { data: transfer, isPending, error } = useStockTransfer(valid ? transferId : undefined);
  const { scan, receive, cancel } = useTransferMutations(valid ? transferId : undefined);

  const [serial, setSerial] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const submitScan = (e: React.FormEvent) => {
    e.preventDefault();
    const value = serial.trim();
    if (!value) return;
    scan.mutate(
      { transferId, serial: value },
      {
        onSuccess: () => {
          setSerial("");
          inputRef.current?.focus();
        },
        onError: (err) => {
          toast.error(
            err instanceof ApiError
              ? err.detail
              : err instanceof Error
                ? err.message
                : "Scan failed",
          );
        },
      },
    );
  };

  if (isPending) {
    return (
      <div>
        <PageHeader title="Stock Transfer" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error || !transfer) {
    return (
      <div>
        <PageHeader title="Stock Transfer" />
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            This transfer could not be loaded.
            <div className="mt-3">
              <Button variant="outline" size="sm" onClick={() => navigate("/inventory/transfers")}>
                Back to transfers
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  const isOpen = transfer.status === "OPEN";
  const scanError =
    scan.error instanceof ApiError
      ? scan.error.detail
      : scan.error instanceof Error
        ? scan.error.message
        : null;

  return (
    <div>
      <PageHeader
        title={`Transfer #${transfer.id}`}
        description={`${transfer.from_location_name} → ${transfer.to_location_name}`}
        actions={<Badge variant={transferStatusVariant(transfer.status)}>{transfer.status}</Badge>}
      />

      <div className="grid gap-4 lg:grid-cols-[2fr_3fr]">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Details</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            <dl className="space-y-2">
              <div className="flex justify-between gap-4 border-b py-1">
                <dt className="text-muted-foreground">From</dt>
                <dd>{transfer.from_location_name}</dd>
              </div>
              <div className="flex justify-between gap-4 border-b py-1">
                <dt className="text-muted-foreground">To</dt>
                <dd>{transfer.to_location_name}</dd>
              </div>
              <div className="flex justify-between gap-4 border-b py-1">
                <dt className="text-muted-foreground">Units</dt>
                <dd>{transfer.line_count}</dd>
              </div>
              <div className="flex justify-between gap-4 border-b py-1">
                <dt className="text-muted-foreground">Created</dt>
                <dd>{new Date(transfer.created_at).toLocaleString()}</dd>
              </div>
              {transfer.completed_at && (
                <div className="flex justify-between gap-4 border-b py-1">
                  <dt className="text-muted-foreground">Completed</dt>
                  <dd>{new Date(transfer.completed_at).toLocaleString()}</dd>
                </div>
              )}
              {transfer.note && (
                <div className="flex justify-between gap-4 py-1">
                  <dt className="text-muted-foreground">Note</dt>
                  <dd className="text-right">{transfer.note}</dd>
                </div>
              )}
            </dl>

            {isOpen && (
              <div className="mt-4 flex gap-2">
                <Button
                  size="sm"
                  disabled={receive.isPending || transfer.line_count === 0}
                  onClick={() =>
                    receive.mutate(transfer.id, {
                      onSuccess: () => toast.success("Transfer received"),
                      onError: (err) =>
                        toast.error(
                          err instanceof ApiError
                            ? err.detail
                            : err instanceof Error
                              ? err.message
                              : "Receive failed",
                        ),
                    })
                  }
                >
                  {receive.isPending ? "Receiving…" : "Receive all"}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={cancel.isPending}
                  onClick={() =>
                    cancel.mutate(transfer.id, {
                      onSuccess: () => toast.success("Transfer cancelled"),
                      onError: (err) =>
                        toast.error(
                          err instanceof ApiError
                            ? err.detail
                            : err instanceof Error
                              ? err.message
                              : "Cancel failed",
                        ),
                    })
                  }
                >
                  Cancel transfer
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Units on this transfer</CardTitle>
          </CardHeader>
          <CardContent>
            {isOpen && (
              <form onSubmit={submitScan} className="mb-3 flex gap-2">
                <Input
                  ref={inputRef}
                  autoFocus
                  placeholder="Scan or type a serial number…"
                  value={serial}
                  onChange={(e) => setSerial(e.target.value)}
                  className="font-mono"
                />
                <Button type="submit" disabled={scan.isPending || !serial.trim()}>
                  {scan.isPending ? "Adding…" : "Add"}
                </Button>
              </form>
            )}

            {scanError && (
              <Alert variant="destructive" className="mb-3">
                <AlertTitle>Couldn&apos;t add that unit</AlertTitle>
                <AlertDescription>{scanError}</AlertDescription>
              </Alert>
            )}

            {transfer.lines.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                No units scanned yet.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                      <th className="px-2 py-2 font-medium">Serial</th>
                      <th className="px-2 py-2 font-medium">SKU</th>
                      <th className="px-2 py-2 font-medium">Unit status</th>
                      <th className="px-2 py-2 font-medium">Received</th>
                    </tr>
                  </thead>
                  <tbody>
                    {transfer.lines.map((line) => (
                      <tr key={line.id} className="border-b last:border-0">
                        <td className="px-2 py-2 font-mono text-xs">{line.serial_number}</td>
                        <td className="px-2 py-2 font-mono text-xs">{line.sku}</td>
                        <td className="px-2 py-2">
                          <Badge variant={stockStatusVariant(line.unit_status)}>
                            {line.unit_status}
                          </Badge>
                        </td>
                        <td className="px-2 py-2">{line.received ? "Yes" : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
