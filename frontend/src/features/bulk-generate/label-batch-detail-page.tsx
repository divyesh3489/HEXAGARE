import { useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Download, Printer, RefreshCw } from "lucide-react";

import { ApiError } from "@/api/client";
import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useLabelBatch, useLabelBatchMutations, useLabelBatchPdf } from "./hooks";
import type { BatchStatus } from "./types";

const statusVariant: Record<BatchStatus, "secondary" | "default" | "destructive"> = {
  PENDING: "secondary",
  READY: "default",
  FAILED: "destructive",
};

export function LabelBatchDetailPage() {
  const params = useParams();
  const navigate = useNavigate();
  const batchId = Number(params.batchId);
  const valid = !Number.isNaN(batchId);

  const { data: batch, isPending, error } = useLabelBatch(valid ? batchId : undefined);
  const { regenerate } = useLabelBatchMutations();
  const pdf = useLabelBatchPdf(valid ? batchId : undefined, batch?.status === "READY");
  const iframeRef = useRef<HTMLIFrameElement>(null);

  if (isPending) {
    return (
      <div>
        <PageHeader title="Label batch" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (error || !batch) {
    return (
      <div>
        <PageHeader title="Label batch" />
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            This label batch could not be loaded.
            <div className="mt-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() => navigate("/products/bulk-generate/history")}
              >
                Back to history
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  const print = () => iframeRef.current?.contentWindow?.print();

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Batch #${batch.id}`}
        description={`${batch.quantity} unit${batch.quantity === 1 ? "" : "s"} of ${batch.variant_sku} at ${batch.location_name}`}
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate("/products/bulk-generate/history")}
          >
            Back to history
          </Button>
        }
      />

      <div className="grid gap-6 md:grid-cols-[1fr_2fr]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span>Units</span>
              <Badge variant={statusVariant[batch.status]}>{batch.status}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 pt-0 text-sm">
            <p className="text-muted-foreground">
              {batch.unit_count} serialized unit{batch.unit_count === 1 ? "" : "s"} created,
              status <span className="font-medium text-foreground">{batch.initial_status}</span>.
            </p>
            {batch.serials.length > 0 && (
              <p className="font-mono text-xs text-muted-foreground">
                {batch.serials[0]}
                {batch.serials.length > 1 && ` … ${batch.serials[batch.serials.length - 1]}`}
              </p>
            )}
            <p className="text-xs text-muted-foreground">
              Label size: {batch.label_size_name} · {batch.barcode_type}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Label sheet</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 pt-0">
            {batch.status === "PENDING" && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <RefreshCw className="size-4 animate-spin" />
                Rendering the PDF… this page will update automatically.
              </div>
            )}

            {batch.status === "FAILED" && (
              <Alert variant="destructive">
                <AlertTitle>PDF generation failed</AlertTitle>
                <AlertDescription className="flex flex-col items-start gap-2">
                  <span>
                    {batch.error_message ||
                      "The label sheet could not be rendered."}{" "}
                    The units were still created.
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={regenerate.isPending}
                    onClick={() => regenerate.mutate(batch.id)}
                  >
                    {regenerate.isPending ? "Retrying…" : "Retry render"}
                  </Button>
                </AlertDescription>
              </Alert>
            )}

            {batch.status === "READY" && (
              <>
                <div className="flex flex-wrap gap-2">
                  {pdf.objectUrl && (
                    <Button asChild size="sm">
                      <a href={pdf.objectUrl} download={`labels-batch-${batch.id}.pdf`}>
                        <Download className="mr-1 size-4" />
                        Download
                      </a>
                    </Button>
                  )}
                  <Button size="sm" variant="outline" onClick={print} disabled={!pdf.objectUrl}>
                    <Printer className="mr-1 size-4" />
                    Print
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={regenerate.isPending}
                    onClick={() => regenerate.mutate(batch.id)}
                  >
                    <RefreshCw className="mr-1 size-4" />
                    Regenerate
                  </Button>
                </div>

                {pdf.isPending && <Skeleton className="h-[600px] w-full" />}
                {pdf.error && (
                  <Alert variant="destructive">
                    <AlertTitle>Couldn’t load the PDF</AlertTitle>
                    <AlertDescription>
                      {pdf.error instanceof ApiError
                        ? pdf.error.detail
                        : pdf.error instanceof Error
                          ? pdf.error.message
                          : "Unknown error."}
                    </AlertDescription>
                  </Alert>
                )}
                {pdf.objectUrl && (
                  <iframe
                    ref={iframeRef}
                    src={pdf.objectUrl}
                    title={`Label sheet for batch ${batch.id}`}
                    className="h-[600px] w-full rounded-md border"
                  />
                )}
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
