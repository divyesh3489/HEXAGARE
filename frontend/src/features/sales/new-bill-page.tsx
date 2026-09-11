import { lazy, Suspense, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ScanLine } from "lucide-react";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useCheckout } from "@/features/billing/hooks";
import { PAYMENT_METHODS, type PaymentEntry, type PaymentMethod } from "@/features/billing/types";
import { variantsApi } from "@/features/products/api";
import { useSale, useSaleCartMutations, useSalesChannels } from "./hooks";
import { saleStatusVariant } from "./status";

// Same code-split reasoning as the standalone scanner route (ADR-011) -- ZXing
// stays out of New Bill's main chunk until the cashier actually opens it.
const CameraScanPanel = lazy(() =>
  import("./camera-scan-panel").then((m) => ({ default: m.CameraScanPanel })),
);

const selectClass =
  "h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

function errMsg(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.detail : err instanceof Error ? err.message : fallback;
}

/** Debounces a raw text input by `delay` ms (same inline pattern as the other
 * search boxes in this app -- no shared hook exists yet). */
function useDebounced(value: string, delay = 300): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const handle = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(handle);
  }, [value, delay]);
  return debounced;
}

function StartBillCard({
  onStart,
  isPending,
}: {
  onStart: (channel: number) => void;
  isPending: boolean;
}) {
  const { data: channels } = useSalesChannels();
  const [channel, setChannel] = useState<number | null>(null);

  useEffect(() => {
    if (channel === null && channels?.data.length) {
      const offline = channels.data.find((c) => c.code === "OFFLINE") ?? channels.data[0];
      setChannel(offline.id);
    }
  }, [channels, channel]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Start a new bill</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-wrap items-center gap-3">
        <select
          className={selectClass}
          value={channel ?? ""}
          onChange={(e) => setChannel(Number(e.target.value))}
        >
          {(channels?.data ?? []).map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <Button disabled={!channel || isPending} onClick={() => channel && onStart(channel)}>
          {isPending ? "Starting…" : "Start bill"}
        </Button>
      </CardContent>
    </Card>
  );
}

function ProductSearch({
  onAdd,
  disabled,
}: {
  onAdd: (variantId: number) => void;
  disabled: boolean;
}) {
  const [text, setText] = useState("");
  const debounced = useDebounced(text);

  const { data, isFetching } = useQuery({
    queryKey: ["billing", "variant-search", debounced],
    queryFn: () => variantsApi.search(debounced),
    enabled: debounced.trim().length >= 2,
  });

  const results = data?.data ?? [];

  return (
    <div className="relative">
      <Input
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Search product by name or SKU…"
        autoComplete="off"
      />
      {debounced.trim().length >= 2 && (
        <Card className="absolute z-10 mt-1 max-h-64 w-full overflow-y-auto py-1">
          {isFetching && <p className="px-3 py-2 text-xs text-muted-foreground">Searching…</p>}
          {!isFetching && results.length === 0 && (
            <p className="px-3 py-2 text-xs text-muted-foreground">No sellable variants match.</p>
          )}
          {results.map((v) => (
            <button
              key={v.id}
              type="button"
              disabled={disabled}
              onClick={() => {
                onAdd(v.id);
                setText("");
              }}
              className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-muted disabled:opacity-50"
            >
              <span>
                <span className="font-mono text-xs text-muted-foreground">{v.sku}</span>
                {v.name ? ` — ${v.name}` : ""}
              </span>
              <span className="text-xs text-muted-foreground">₹{v.effective_selling_price}</span>
            </button>
          ))}
        </Card>
      )}
    </div>
  );
}

export function NewBillPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const resumeParam = Number(searchParams.get("sale"));
  const initialSaleId = Number.isFinite(resumeParam) && resumeParam > 0 ? resumeParam : null;

  const [saleId, setSaleId] = useState<number | null>(initialSaleId);
  const [code, setCode] = useState("");
  const [scanning, setScanning] = useState(false);
  const [payments, setPayments] = useState<PaymentEntry[]>([{ method: "CASH", amount: "" }]);

  const { data: sale, isPending: salePending } = useSale(saleId ?? undefined);
  const { create, addUnit, removeLine, cancel } = useSaleCartMutations(saleId ?? undefined);
  const checkout = useCheckout();

  const isEditableCart = sale?.status === "DRAFT";
  const isPayable = sale?.status === "DRAFT" || sale?.status === "RESERVED";

  const addUnitByCode = (value: string) => {
    if (!value || !isEditableCart) return;
    addUnit.mutate(
      { code: value },
      { onError: (err) => toast.error(errMsg(err, "Couldn't add that unit")) },
    );
  };

  const submitCode = (e: FormEvent) => {
    e.preventDefault();
    const value = code.trim();
    if (!value) return;
    addUnitByCode(value);
    setCode("");
  };

  const addByVariant = (variantId: number) => {
    if (!isEditableCart) return;
    addUnit.mutate(
      { variant: variantId },
      { onError: (err) => toast.error(errMsg(err, "Couldn't add that product")) },
    );
  };

  const updatePayment = (index: number, patch: Partial<PaymentEntry>) => {
    setPayments((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  };

  const tenderedNow = payments.reduce((sum, row) => sum + (Number(row.amount) || 0), 0);
  const balanceDue = sale ? Number(sale.balance_due) : 0;

  const handleComplete = () => {
    if (!saleId) return;
    const validPayments = payments.filter((row) => Number(row.amount) > 0);
    checkout.mutate(
      { sale: saleId, payments: validPayments },
      {
        onSuccess: (result) => {
          if (result.invoice) {
            toast.success(`Sale completed — ${result.invoice.invoice_number}`);
            navigate(`/sales/invoices/${result.invoice.id}`);
          } else {
            toast(
              `Payment recorded — ₹${result.sale.balance_due} still due. Bill is on hold.`,
            );
            setPayments([{ method: "CASH", amount: "" }]);
          }
        },
        onError: (err) => toast.error(errMsg(err, "Couldn't record the payment")),
      },
    );
  };

  const handleCancel = () => {
    cancel.mutate(undefined, {
      onSuccess: () => {
        toast.success("Bill cancelled");
        navigate("/sales/orders");
      },
      onError: (err) => toast.error(errMsg(err, "Couldn't cancel the bill")),
    });
  };

  if (initialSaleId && salePending) {
    return (
      <div className="mx-auto max-w-3xl">
        <PageHeader title="New Bill" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (initialSaleId && sale && sale.status !== "DRAFT" && sale.status !== "RESERVED") {
    return (
      <div className="mx-auto max-w-3xl">
        <PageHeader title="New Bill" />
        <Card>
          <CardContent className="space-y-3 py-12 text-center text-sm text-muted-foreground">
            <p>
              Order #{sale.id} is {sale.status} — it can&apos;t be resumed here.
            </p>
            <Link to="/sales/orders" className="text-primary hover:underline">
              Back to orders
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="New Bill"
        description="Scan or search to add units, take payment, and complete the sale."
        actions={
          sale ? <Badge variant={saleStatusVariant(sale.status)}>{sale.status}</Badge> : undefined
        }
      />

      {!saleId && (
        <StartBillCard
          isPending={create.isPending}
          onStart={(channel) =>
            create.mutate(channel, {
              onSuccess: (created) => setSaleId(created.id),
              onError: (err) => toast.error(errMsg(err, "Couldn't start a new bill")),
            })
          }
        />
      )}

      {sale && (
        <div className="space-y-4">
          {isEditableCart && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Add to bill</CardTitle>
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
                  <Button type="submit" disabled={addUnit.isPending || !code.trim()}>
                    {addUnit.isPending ? "Adding…" : "Add"}
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
                    <CameraScanPanel
                      onAdd={addUnitByCode}
                      onClose={() => setScanning(false)}
                    />
                  </Suspense>
                )}

                <ProductSearch onAdd={addByVariant} disabled={addUnit.isPending} />
              </CardContent>
            </Card>
          )}

          {!isEditableCart && (
            <Alert>
              <AlertTitle>Bill on hold — cart is locked</AlertTitle>
              <AlertDescription>
                This bill already went through checkout, so items can&apos;t be added or removed.
                Record more payment below to complete it.
              </AlertDescription>
            </Alert>
          )}

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Cart</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {sale.lines.length === 0 ? (
                <p className="px-4 py-8 text-center text-sm text-muted-foreground">
                  No items yet — scan a barcode or search for a product above.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                        <th className="px-4 py-2 font-medium">Product</th>
                        <th className="px-4 py-2 font-medium">SKU</th>
                        <th className="px-4 py-2 text-right font-medium">Qty</th>
                        <th className="px-4 py-2 text-right font-medium">Price</th>
                        <th className="px-4 py-2 text-right font-medium">Total</th>
                        {isEditableCart && <th className="px-4 py-2" />}
                      </tr>
                    </thead>
                    <tbody>
                      {sale.lines.map((line) => (
                        <tr key={line.id} className="border-b last:border-0">
                          <td className="px-4 py-2">{line.product_name}</td>
                          <td className="px-4 py-2 font-mono text-xs">{line.sku}</td>
                          <td className="px-4 py-2 text-right">{line.quantity}</td>
                          <td className="px-4 py-2 text-right">₹{line.unit_price}</td>
                          <td className="px-4 py-2 text-right font-medium">₹{line.net_amount}</td>
                          {isEditableCart && (
                            <td className="px-4 py-2 text-right">
                              <Button
                                size="sm"
                                variant="ghost"
                                disabled={removeLine.isPending}
                                onClick={() =>
                                  removeLine.mutate(line.id, {
                                    onError: (err) =>
                                      toast.error(errMsg(err, "Couldn't remove that line")),
                                  })
                                }
                              >
                                Remove
                              </Button>
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>

          {sale.lines.length > 0 && (
            <>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Totals</CardTitle>
                </CardHeader>
                <CardContent className="space-y-1 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Subtotal</span>
                    <span>₹{sale.subtotal}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Discount</span>
                    <span>₹{sale.discount_total}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Tax</span>
                    <span>₹{sale.tax_total}</span>
                  </div>
                  <div className="flex justify-between border-t pt-1 font-semibold">
                    <span>Grand total</span>
                    <span>₹{sale.grand_total}</span>
                  </div>
                  {Number(sale.amount_paid) > 0 && (
                    <>
                      <div className="flex justify-between pt-2">
                        <span className="text-muted-foreground">Already paid</span>
                        <span>₹{sale.amount_paid}</span>
                      </div>
                      <div className="flex justify-between font-medium text-amber-600">
                        <span>Balance due</span>
                        <span>₹{sale.balance_due}</span>
                      </div>
                    </>
                  )}
                </CardContent>
              </Card>

              {isPayable && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">Payment</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {payments.map((row, i) => (
                      <div key={i} className="flex gap-2">
                        <select
                          className={selectClass}
                          value={row.method}
                          onChange={(e) =>
                            updatePayment(i, { method: e.target.value as PaymentMethod })
                          }
                        >
                          {PAYMENT_METHODS.map((m) => (
                            <option key={m} value={m}>
                              {m}
                            </option>
                          ))}
                        </select>
                        <Input
                          type="number"
                          min="0"
                          step="0.01"
                          value={row.amount}
                          onChange={(e) => updatePayment(i, { amount: e.target.value })}
                          placeholder="Amount"
                          className="flex-1"
                        />
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={payments.length === 1}
                          onClick={() => setPayments((rows) => rows.filter((_, idx) => idx !== i))}
                        >
                          Remove
                        </Button>
                      </div>
                    ))}
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        setPayments((rows) => [...rows, { method: "CASH", amount: "" }])
                      }
                    >
                      Add payment
                    </Button>

                    <div className="flex justify-between border-t pt-2 text-sm">
                      <span className="text-muted-foreground">Amount tendered now</span>
                      <span>₹{tenderedNow.toFixed(2)}</span>
                    </div>
                    {tenderedNow < balanceDue && (
                      <Alert>
                        <AlertTitle>Balance will still be due</AlertTitle>
                        <AlertDescription>
                          ₹{(balanceDue - tenderedNow).toFixed(2)} will remain on hold after this
                          payment — the bill stays RESERVED until it&apos;s fully paid.
                        </AlertDescription>
                      </Alert>
                    )}
                  </CardContent>
                </Card>
              )}

              <div className="flex justify-end gap-2">
                {isPayable && (
                  <Button variant="outline" disabled={cancel.isPending} onClick={handleCancel}>
                    Cancel bill
                  </Button>
                )}
                {isPayable && (
                  <Button disabled={checkout.isPending} onClick={handleComplete}>
                    {checkout.isPending
                      ? "Saving…"
                      : tenderedNow >= balanceDue
                        ? "Complete sale"
                        : "Record payment"}
                  </Button>
                )}
              </div>
            </>
          )}

          {sale.lines.length === 0 && isEditableCart && (
            <div className="flex justify-end">
              <Button variant="outline" disabled={cancel.isPending} onClick={handleCancel}>
                Cancel bill
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
