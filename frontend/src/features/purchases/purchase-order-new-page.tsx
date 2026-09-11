import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "@/api/client";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useProducts, useVariants } from "@/features/products/hooks";
import { useSuppliers } from "@/features/suppliers/hooks";
import { usePurchaseOrderMutations } from "./hooks";
import type { PurchaseOrderLineInput } from "./types";

const selectClass =
  "h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

interface DraftLine extends PurchaseOrderLineInput {
  sku: string;
  name: string;
}

export function NewPurchaseOrderPage() {
  const navigate = useNavigate();
  const { data: suppliersData } = useSuppliers({ page_size: 200 });
  const suppliers = suppliersData?.data ?? [];

  const [supplierId, setSupplierId] = useState("");
  const [reference, setReference] = useState("");
  const [invoiceNumber, setInvoiceNumber] = useState("");
  const [note, setNote] = useState("");
  const [lines, setLines] = useState<DraftLine[]>([]);

  const { data: productsData } = useProducts({ page_size: 200 });
  const products = productsData?.data ?? [];
  const [productId, setProductId] = useState("");
  const { data: variantsData } = useVariants(productId ? Number(productId) : -1);
  const variants = variantsData?.data ?? [];
  const [variantId, setVariantId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [unitPrice, setUnitPrice] = useState("");
  const [taxRate, setTaxRate] = useState("");

  const { create } = usePurchaseOrderMutations();
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const selectedVariant = variants.find((v) => String(v.id) === variantId);

  const addLine = () => {
    if (!selectedVariant || !quantity || !unitPrice) return;
    setLines((prev) => [
      ...prev,
      {
        variant: selectedVariant.id,
        quantity_ordered: Number(quantity),
        unit_price: unitPrice,
        tax_rate: taxRate || undefined,
        sku: selectedVariant.sku,
        name: selectedVariant.name || selectedVariant.sku,
      },
    ]);
    setProductId("");
    setVariantId("");
    setQuantity("1");
    setUnitPrice("");
    setTaxRate("");
  };

  const removeLine = (index: number) => {
    setLines((prev) => prev.filter((_, i) => i !== index));
  };

  const submit = async () => {
    setFormError(null);
    setFieldErrors({});
    if (!supplierId) {
      setFormError("Choose a supplier.");
      return;
    }
    try {
      const order = await create.mutateAsync({
        supplier: Number(supplierId),
        reference: reference || undefined,
        invoice_number: invoiceNumber || undefined,
        note: note || undefined,
        lines: lines.map(({ sku: _sku, name: _name, ...line }) => line),
      });
      navigate(`/purchases/orders/${order.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.fields) {
        setFieldErrors(err.fields);
        setFormError(err.message);
      } else {
        setFormError(err instanceof Error ? err.message : "Could not create the purchase order.");
      }
    }
  };

  return (
    <div className="max-w-3xl">
      <PageHeader
        title="New Purchase Order"
        description="Order stock from a supplier. Lines are editable until the order is placed."
      />

      <Card className="mb-4">
        <CardContent className="space-y-4 py-5">
          {formError && <p className="text-sm text-destructive">{formError}</p>}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label>Supplier</Label>
              <select
                value={supplierId}
                onChange={(e) => setSupplierId(e.target.value)}
                className={selectClass}
              >
                <option value="">Select…</option>
                {suppliers.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
              {fieldErrors.supplier && (
                <p className="text-xs text-destructive">{fieldErrors.supplier.join(" ")}</p>
              )}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Reference (optional)</Label>
              <Input value={reference} onChange={(e) => setReference(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Supplier invoice number (optional)</Label>
              <Input value={invoiceNumber} onChange={(e) => setInvoiceNumber(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Note (optional)</Label>
              <Input value={note} onChange={(e) => setNote(e.target.value)} />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="mb-4">
        <CardContent className="space-y-4 py-5">
          <h3 className="font-medium">Add a line</h3>
          <div className="grid gap-4 sm:grid-cols-5">
            <div className="flex flex-col gap-1.5 sm:col-span-2">
              <Label>Product</Label>
              <select
                value={productId}
                onChange={(e) => {
                  setProductId(e.target.value);
                  setVariantId("");
                }}
                className={selectClass}
              >
                <option value="">Select…</option>
                {products.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1.5 sm:col-span-2">
              <Label>Variant</Label>
              <select
                value={variantId}
                onChange={(e) => {
                  const id = e.target.value;
                  setVariantId(id);
                  const v = variants.find((x) => String(x.id) === id);
                  if (v) {
                    setUnitPrice(v.effective_purchase_price ?? "");
                    setTaxRate(v.effective_tax_rate ?? "");
                  }
                }}
                disabled={!productId}
                className={selectClass}
              >
                <option value="">{productId ? "Select…" : "Pick a product first"}</option>
                {variants.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.sku}
                    {v.name ? ` — ${v.name}` : ""}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Quantity</Label>
              <input
                type="number"
                min={1}
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                className={selectClass}
              />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="flex flex-col gap-1.5">
              <Label>Unit price</Label>
              <input
                type="number"
                step="0.01"
                min={0}
                value={unitPrice}
                onChange={(e) => setUnitPrice(e.target.value)}
                className={selectClass}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Tax rate %</Label>
              <input
                type="number"
                step="0.01"
                min={0}
                value={taxRate}
                onChange={(e) => setTaxRate(e.target.value)}
                className={selectClass}
              />
            </div>
            <div className="flex items-end">
              <Button
                type="button"
                variant="outline"
                onClick={addLine}
                disabled={!selectedVariant || !quantity || !unitPrice}
              >
                Add line
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="mb-4">
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-2 font-medium">SKU</th>
                  <th className="px-4 py-2 font-medium">Variant</th>
                  <th className="px-4 py-2 text-right font-medium">Qty</th>
                  <th className="px-4 py-2 text-right font-medium">Unit price</th>
                  <th className="px-4 py-2 text-right font-medium">Tax %</th>
                  <th className="px-4 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {lines.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                      No lines added yet.
                    </td>
                  </tr>
                )}
                {lines.map((line, i) => (
                  <tr key={i} className="border-b last:border-0">
                    <td className="px-4 py-2 font-mono text-xs">{line.sku}</td>
                    <td className="px-4 py-2">{line.name}</td>
                    <td className="px-4 py-2 text-right">{line.quantity_ordered}</td>
                    <td className="px-4 py-2 text-right">₹{line.unit_price}</td>
                    <td className="px-4 py-2 text-right">{line.tax_rate ?? "—"}</td>
                    <td className="px-4 py-2 text-right">
                      <Button size="sm" variant="ghost" onClick={() => removeLine(i)}>
                        Remove
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <div className="flex gap-2">
        <Button onClick={submit} disabled={create.isPending || !supplierId}>
          {create.isPending ? "Creating…" : "Create purchase order"}
        </Button>
        <Button type="button" variant="outline" onClick={() => navigate("/purchases/orders")}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
