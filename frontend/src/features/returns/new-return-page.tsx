import { lazy, Suspense, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ScanLine } from "lucide-react";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { PAYMENT_METHODS, type PaymentMethod } from "@/features/billing/types";
import { useCreateReturn, useResolveReturnCode } from "./hooks";
import type { ReturnEntryDraft } from "./types";

// Same code-split reasoning as New Bill (ADR-011) -- ZXing stays out of this
// page's main chunk until the cashier opens the camera.
const CameraScanPanel = lazy(() =>
  import("@/features/sales/camera-scan-panel").then((m) => ({ default: m.CameraScanPanel })),
);

const selectClass =
  "h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

function errMsg(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.detail : err instanceof Error ? err.message : fallback;
}

export function NewReturnPage() {
  const navigate = useNavigate();
  const [code, setCode] = useState("");
  const [scanning, setScanning] = useState(false);
  const [entries, setEntries] = useState<ReturnEntryDraft[]>([]);
  const [reason, setReason] = useState("");
  const [refundMethod, setRefundMethod] = useState<PaymentMethod>("CASH");
  const [note, setNote] = useState("");

  const resolveCode = useResolveReturnCode();
  const createReturn = useCreateReturn();

  const addByCode = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed) return;
    if (entries.some((e) => e.code === trimmed)) {
      toast.error(`${trimmed} was already scanned.`);
      return;
    }
    resolveCode.mutate(trimmed, {
      onSuccess: (preview) => {
        setEntries((rows) => [
          ...rows,
          { code: trimmed, refund_amount: preview.suggested_refund_amount, preview },
        ]);
      },
      onError: (err) => toast.error(errMsg(err, "Couldn't resolve that serial")),
    });
  };

  const submitCode = (e: FormEvent) => {
    e.preventDefault();
    addByCode(code);
    setCode("");
  };

  const removeEntry = (entryCode: string) => {
    setEntries((rows) => rows.filter((row) => row.code !== entryCode));
  };

  const updateRefundAmount = (entryCode: string, value: string) => {
    setEntries((rows) =>
      rows.map((row) => (row.code === entryCode ? { ...row, refund_amount: value } : row)),
    );
  };

  const refundTotal = entries.reduce((sum, e) => sum + (Number(e.refund_amount) || 0), 0);

  const submit = () => {
    if (entries.length === 0 || !reason.trim()) return;
    createReturn.mutate(
      {
        entries: entries.map((e) => ({ code: e.code, refund_amount: e.refund_amount })),
        reason: reason.trim(),
        refund_method: refundMethod,
        note: note.trim() || undefined,
      },
      {
        onSuccess: (created) => {
          toast.success(`Return #${created.id} created`);
          navigate(`/sales/returns/${created.id}`);
        },
        onError: (err) => toast.error(errMsg(err, "Couldn't create the return")),
      },
    );
  };

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="New Return"
        description="Scan or search the sold serial to return, then confirm the refund."
      />

      <div className="space-y-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Scan a sold unit</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <form onSubmit={submitCode} className="flex gap-2">
              <Input
                autoFocus
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="Scan or type a serial / barcode…"
                className="font-mono"
              />
              <Button type="submit" disabled={resolveCode.isPending || !code.trim()}>
                {resolveCode.isPending ? "Looking up…" : "Add"}
              </Button>
              <Button
                type="button"
                variant="outline"
                size="icon"
                onClick={() => setScanning((s) => !s)}
                aria-label="Scan with camera"
              >
                <ScanLine />
              </Button>
            </form>

            {scanning && (
              <Suspense fallback={<Skeleton className="aspect-video w-full" />}>
                <CameraScanPanel onAdd={addByCode} onClose={() => setScanning(false)} />
              </Suspense>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Units to return</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {entries.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-muted-foreground">
                No units scanned yet.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                      <th className="px-4 py-2 font-medium">Product</th>
                      <th className="px-4 py-2 font-medium">Serial</th>
                      <th className="px-4 py-2 font-medium">Sale</th>
                      <th className="px-4 py-2 text-right font-medium">Refund amount</th>
                      <th className="px-4 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {entries.map((entry) => (
                      <tr key={entry.code} className="border-b last:border-0">
                        <td className="px-4 py-2">
                          {entry.preview.product_name}{" "}
                          <span className="font-mono text-xs text-muted-foreground">
                            {entry.preview.sku}
                          </span>
                        </td>
                        <td className="px-4 py-2 font-mono text-xs">{entry.preview.serial_number}</td>
                        <td className="px-4 py-2">#{entry.preview.sale}</td>
                        <td className="px-4 py-2 text-right">
                          <Input
                            type="number"
                            min="0"
                            step="0.01"
                            value={entry.refund_amount}
                            onChange={(e) => updateRefundAmount(entry.code, e.target.value)}
                            className="w-28 text-right"
                          />
                        </td>
                        <td className="px-4 py-2 text-right">
                          <Button size="sm" variant="ghost" onClick={() => removeEntry(entry.code)}>
                            Remove
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        {entries.length > 0 && (
          <>
            {new Set(entries.map((e) => e.preview.sale)).size > 1 && (
              <Alert variant="destructive">
                <AlertTitle>Units belong to different sales</AlertTitle>
                <AlertDescription>
                  A return covers one sale at a time — remove the units that don&apos;t belong to
                  the same sale before submitting.
                </AlertDescription>
              </Alert>
            )}

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Refund</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <Input
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Reason for return (required)…"
                />
                <div className="flex items-center gap-2">
                  <span className="text-sm text-muted-foreground">Refund method</span>
                  <select
                    className={selectClass}
                    value={refundMethod}
                    onChange={(e) => setRefundMethod(e.target.value as PaymentMethod)}
                  >
                    {PAYMENT_METHODS.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                </div>
                <Input
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Note (optional)…"
                />
                <div className="flex justify-between border-t pt-2 text-sm font-semibold">
                  <span>Total refund</span>
                  <span>₹{refundTotal.toFixed(2)}</span>
                </div>
              </CardContent>
            </Card>

            <div className="flex justify-end">
              <Button
                disabled={
                  createReturn.isPending ||
                  !reason.trim() ||
                  new Set(entries.map((e) => e.preview.sale)).size > 1
                }
                onClick={submit}
              >
                {createReturn.isPending ? "Creating…" : "Create return"}
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
