import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "@/api/client";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { useProducts, useVariants } from "@/features/products/hooks";
import {
  useLabelBatchLocations,
  useLabelBatchMutations,
  useLabelSizes,
  useNextSerial,
} from "./hooks";
import { INITIAL_STATUSES } from "./types";

const selectClass =
  "h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

const CONTENT_FLAGS = [
  { key: "include_product_name", label: "Product name" },
  { key: "include_variant", label: "Variant" },
  { key: "include_sku", label: "SKU" },
  { key: "include_mrp", label: "MRP" },
  { key: "include_selling_price", label: "Selling price" },
] as const;

type FlagKey = (typeof CONTENT_FLAGS)[number]["key"];

export function BulkGeneratePage() {
  const navigate = useNavigate();

  const { data: productsData } = useProducts({ page_size: 200 });
  const products = productsData?.data ?? [];

  const [productId, setProductId] = useState("");
  const { data: variantsData } = useVariants(productId ? Number(productId) : -1);
  const variants = variantsData?.data ?? [];

  const [variantId, setVariantId] = useState("");
  const [quantity, setQuantity] = useState("100");
  const [initialStatus, setInitialStatus] = useState<(typeof INITIAL_STATUSES)[number]>(
    "AVAILABLE",
  );
  const [locationId, setLocationId] = useState("");
  const [labelSizeId, setLabelSizeId] = useState("");
  const [customText, setCustomText] = useState("");
  const [flags, setFlags] = useState<Record<FlagKey, boolean>>({
    include_product_name: true,
    include_variant: true,
    include_sku: true,
    include_mrp: false,
    include_selling_price: false,
  });

  const { data: locationsData } = useLabelBatchLocations();
  const locations = (locationsData?.data ?? []).filter((l) => l.is_active);
  const { data: labelSizesData } = useLabelSizes();
  const labelSizes = useMemo(() => labelSizesData?.data ?? [], [labelSizesData]);

  const { data: nextSerial } = useNextSerial(variantId ? Number(variantId) : undefined);
  const { create } = useLabelBatchMutations();

  const qtyNumber = Number(quantity);
  const canSubmit =
    !!variantId &&
    !!locationId &&
    !!labelSizeId &&
    Number.isInteger(qtyNumber) &&
    qtyNumber >= 1 &&
    qtyNumber <= 5000;

  // Default the label size to the marked default once loaded.
  const resolvedLabelSizeId = useMemo(() => {
    if (labelSizeId) return labelSizeId;
    const fallback = labelSizes.find((s) => s.is_default) ?? labelSizes[0];
    return fallback ? String(fallback.id) : "";
  }, [labelSizeId, labelSizes]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    create.mutate(
      {
        variant: Number(variantId),
        location: Number(locationId),
        quantity: qtyNumber,
        initial_status: initialStatus,
        label_size: Number(resolvedLabelSizeId),
        custom_text: customText || undefined,
        ...flags,
      },
      { onSuccess: (batch) => navigate(`/products/bulk-generate/${batch.id}`) },
    );
  };

  const error = create.error;
  const fieldError = (name: string) =>
    error instanceof ApiError ? error.fieldError(name) : undefined;

  return (
    <div className="max-w-2xl">
      <PageHeader
        title="Bulk Generate Units"
        description="Create serialized units for a variant and a printable label sheet."
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate("/products/bulk-generate/history")}
          >
            History
          </Button>
        }
      />

      <Card>
        <CardContent className="pt-6">
          <form onSubmit={submit} className="flex flex-col gap-4">
            <div>
              <Label htmlFor="product">Product</Label>
              <select
                id="product"
                value={productId}
                onChange={(e) => {
                  setProductId(e.target.value);
                  setVariantId("");
                }}
                required
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

            <div>
              <Label htmlFor="variant">Variant</Label>
              <select
                id="variant"
                value={variantId}
                onChange={(e) => setVariantId(e.target.value)}
                required
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
              {fieldError("variant") && (
                <p className="mt-1 text-xs text-destructive">{fieldError("variant")}</p>
              )}
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <Label htmlFor="quantity">Quantity</Label>
                <input
                  id="quantity"
                  type="number"
                  min={1}
                  max={5000}
                  value={quantity}
                  onChange={(e) => setQuantity(e.target.value)}
                  required
                  className={selectClass}
                />
                {fieldError("quantity") && (
                  <p className="mt-1 text-xs text-destructive">{fieldError("quantity")}</p>
                )}
              </div>
              <div>
                <Label htmlFor="status">Initial status</Label>
                <select
                  id="status"
                  value={initialStatus}
                  onChange={(e) =>
                    setInitialStatus(e.target.value as (typeof INITIAL_STATUSES)[number])
                  }
                  className={selectClass}
                >
                  {INITIAL_STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <Label htmlFor="location">Location</Label>
                <select
                  id="location"
                  value={locationId}
                  onChange={(e) => setLocationId(e.target.value)}
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
                {fieldError("location") && (
                  <p className="mt-1 text-xs text-destructive">{fieldError("location")}</p>
                )}
              </div>
              <div>
                <Label htmlFor="label-size">Label size</Label>
                <select
                  id="label-size"
                  value={resolvedLabelSizeId}
                  onChange={(e) => setLabelSizeId(e.target.value)}
                  required
                  className={selectClass}
                >
                  <option value="">Select…</option>
                  {labelSizes.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <fieldset className="rounded-md border p-3">
              <legend className="px-1 text-xs font-medium text-muted-foreground">
                Label content
              </legend>
              <div className="flex flex-wrap gap-x-4 gap-y-2">
                {CONTENT_FLAGS.map((f) => (
                  <label key={f.key} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={flags[f.key]}
                      onChange={(e) =>
                        setFlags((prev) => ({ ...prev, [f.key]: e.target.checked }))
                      }
                    />
                    {f.label}
                  </label>
                ))}
              </div>
              <div className="mt-3">
                <Label htmlFor="custom-text">Custom text (optional)</Label>
                <input
                  id="custom-text"
                  value={customText}
                  maxLength={120}
                  onChange={(e) => setCustomText(e.target.value)}
                  className={selectClass}
                  placeholder="e.g. Handle with care"
                />
              </div>
            </fieldset>

            {variantId && nextSerial && (
              <p className="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">
                Serials will start at{" "}
                <span className="font-mono text-foreground">{nextSerial.serial_number}</span>{" "}
                (preview — the real value is assigned when you generate).
              </p>
            )}

            {error && !fieldError("variant") && !fieldError("quantity") && !fieldError("location") && (
              <p className="text-sm text-destructive">
                {error instanceof ApiError
                  ? error.detail
                  : error instanceof Error
                    ? error.message
                    : "Couldn't generate the batch."}
              </p>
            )}

            <div className="flex gap-2">
              <Button type="submit" disabled={!canSubmit || create.isPending}>
                {create.isPending ? "Generating…" : `Generate ${qtyNumber || 0} units`}
              </Button>
              <Button type="button" variant="outline" onClick={() => navigate("/products/units")}>
                Cancel
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
