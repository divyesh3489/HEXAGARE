import { useRef, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/client";
import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useImportBatch, useUploadImport } from "./hooks";
import { importBatchStatusVariant } from "./status";

const IN_PROGRESS = new Set(["PENDING", "PROCESSING"]);

export function AmazonImportPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [batchId, setBatchId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const upload = useUploadImport();
  const batchQuery = useImportBatch(batchId ?? undefined);
  const batch = batchQuery.data;

  const submit = async () => {
    if (!file) return;
    setError(null);
    try {
      const created = await upload.mutateAsync(file);
      setBatchId(created.id);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Upload failed.");
    }
  };

  return (
    <div>
      <PageHeader
        title="Import Amazon orders"
        description="Upload an Amazon order CSV export. Import runs in the background -- this page follows it through to done."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" asChild>
              <a href="/samples/amazon-orders-sample.csv" download="amazon-orders-sample.csv">
                Download sample CSV
              </a>
            </Button>
            <Button variant="outline" asChild>
              <Link to="/integrations/amazon/imports">Import history</Link>
            </Button>
          </div>
        }
      />

      <Card className="mb-4">
        <CardContent className="space-y-4 py-5">
          <div className="flex flex-wrap items-center gap-3">
            <input
              ref={inputRef}
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="text-sm"
            />
            <Button onClick={submit} disabled={!file || upload.isPending}>
              {upload.isPending ? "Uploading…" : "Upload & import"}
            </Button>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <p className="text-xs text-muted-foreground">
            Download the sample CSV above to see the expected columns and format (also documented
            in <code>docs/amazon-order-import.md</code>). One row per order line; an unmapped
            Amazon SKU or a status the importer doesn&apos;t recognise fails just that order -- the
            rest of the file still imports.
          </p>
        </CardContent>
      </Card>

      {batch && (
        <Card>
          <CardContent className="space-y-4 py-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="font-medium">Batch #{batch.id}</h3>
              <Badge variant={importBatchStatusVariant(batch.status)}>
                {IN_PROGRESS.has(batch.status) ? `${batch.status}…` : batch.status}
              </Badge>
            </div>

            <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
              <Stat label="Rows" value={batch.total_rows} />
              <Stat label="Orders" value={batch.total_orders} />
              <Stat label="Created" value={batch.orders_created} />
              <Stat label="Updated" value={batch.orders_updated} />
              <Stat label="Failed" value={batch.orders_failed} />
            </div>

            {batch.error_message && (
              <Alert variant="destructive">
                <AlertTitle>Import failed</AlertTitle>
                <AlertDescription>{batch.error_message}</AlertDescription>
              </Alert>
            )}

            {batch.error_log.length > 0 && (
              <div className="rounded-md border">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                      <th className="px-3 py-2 font-medium">Row / order</th>
                      <th className="px-3 py-2 font-medium">Message</th>
                    </tr>
                  </thead>
                  <tbody>
                    {batch.error_log.map((entry, i) => (
                      <tr key={i} className="border-b last:border-0">
                        <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                          {entry.order_id ?? `row ${entry.row}`}
                        </td>
                        <td className="px-3 py-2">{entry.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-lg font-semibold">{value}</div>
    </div>
  );
}
