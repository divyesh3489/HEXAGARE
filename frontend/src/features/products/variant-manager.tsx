import { useMemo, useState } from "react";

import { ApiError } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useAttributeMutations,
  useAttributes,
  useImages,
  useVariantMutations,
  useVariants,
} from "./hooks";
import { SkuField } from "./sku-field";
import type { Product, ProductImage, ProductVariant } from "./types";

interface AttrRow {
  attribute: number | "";
  value: string;
}

/** Price fields — empty string means "inherit the product default". */
const PRICE_KEYS = ["mrp", "selling_price", "purchase_price", "tax_rate"] as const;
type PriceKey = (typeof PRICE_KEYS)[number];

const PRICE_LABELS: Record<PriceKey, string> = {
  mrp: "MRP",
  selling_price: "Selling price (incl. GST)",
  purchase_price: "Purchase price",
  tax_rate: "GST rate (%)",
};

interface Draft {
  name: string;
  code: string;
  sku: string;
  barcode: string;
  mrp: string;
  selling_price: string;
  purchase_price: string;
  tax_rate: string;
  is_active: boolean;
  rows: AttrRow[];
}

const EMPTY: Draft = {
  name: "",
  code: "",
  sku: "",
  barcode: "",
  mrp: "",
  selling_price: "",
  purchase_price: "",
  tax_rate: "",
  is_active: true,
  rows: [],
};

function toDraft(v: ProductVariant): Draft {
  return {
    name: v.name,
    code: v.code,
    sku: v.sku,
    barcode: v.barcode,
    mrp: v.mrp ?? "",
    selling_price: v.selling_price ?? "",
    purchase_price: v.purchase_price ?? "",
    tax_rate: v.tax_rate ?? "",
    is_active: v.is_active,
    rows: v.attribute_values.map((a) => ({ attribute: a.attribute, value: a.value })),
  };
}

function gstPreview(sellingPrice: number, taxRate: number) {
  if (!Number.isFinite(sellingPrice) || !Number.isFinite(taxRate) || sellingPrice <= 0) {
    return null;
  }
  const base = sellingPrice / (1 + taxRate / 100);
  const round = (n: number) => (Math.round((n + Number.EPSILON) * 100) / 100).toFixed(2);
  return {
    base: round(base),
    gst: round(sellingPrice - base),
    total: sellingPrice.toFixed(2),
  };
}

const STATUS_BADGE: Record<
  string,
  { label: string; variant: "default" | "muted" | "destructive" }
> = {
  active: { label: "Active", variant: "default" },
  inactive: { label: "Inactive", variant: "muted" },
  draft: { label: "Draft", variant: "muted" },
  discontinued: { label: "Discontinued", variant: "destructive" },
};

function StatusBadge({ status }: { status: string }) {
  const s = STATUS_BADGE[status] ?? STATUS_BADGE.inactive;
  return <Badge variant={s.variant}>{s.label}</Badge>;
}

function VariantThumbnails({ images }: { images: ProductImage[] }) {
  if (images.length === 0) {
    return <span className="text-muted-foreground">—</span>;
  }
  return (
    <div className="flex items-center gap-1">
      {images.slice(0, 3).map((img) => (
        <div key={img.id} className="size-8 overflow-hidden rounded border bg-muted">
          {img.image_url && (
            <img src={img.image_url} alt="" className="h-full w-full object-cover" />
          )}
        </div>
      ))}
      {images.length > 3 && (
        <span className="text-xs text-muted-foreground">+{images.length - 3}</span>
      )}
    </div>
  );
}

export function VariantManager({ product }: { product: Product }) {
  const variantsQuery = useVariants(product.id);
  const attributesQuery = useAttributes();
  const imagesQuery = useImages(product.id);
  const { create, update, remove } = useVariantMutations(product.id);
  const { create: createAttribute } = useAttributeMutations();

  const [editingId, setEditingId] = useState<number | "new" | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [newAttrName, setNewAttrName] = useState("");

  const attributes = attributesQuery.data?.data ?? [];
  const variants = variantsQuery.data?.data ?? [];
  const images = imagesQuery.data?.data ?? [];

  /** Product default for a price field, or "" if the product has none. */
  const productDefault = (key: PriceKey): string => product[key] ?? "";

  const preview = useMemo(
    () =>
      gstPreview(
        Number(draft.selling_price.trim() || product.selling_price || ""),
        Number(draft.tax_rate.trim() || product.tax_rate || "0"),
      ),
    [draft.selling_price, draft.tax_rate, product.selling_price, product.tax_rate],
  );

  const startNew = () => {
    setDraft(EMPTY);
    setEditingId("new");
    setFormError(null);
    setFieldErrors({});
  };

  const startEdit = (v: ProductVariant) => {
    setDraft(toDraft(v));
    setEditingId(v.id);
    setFormError(null);
    setFieldErrors({});
  };

  const cancel = () => {
    setEditingId(null);
    setDraft(EMPTY);
  };

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));

  const addRow = () => set("rows", [...draft.rows, { attribute: "", value: "" }]);
  const updateRow = (i: number, patch: Partial<AttrRow>) =>
    set(
      "rows",
      draft.rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)),
    );
  const removeRow = (i: number) =>
    set(
      "rows",
      draft.rows.filter((_, idx) => idx !== i),
    );

  const submit = async () => {
    setFormError(null);
    setFieldErrors({});
    const payload = {
      product: product.id,
      name: draft.name,
      code: draft.code,
      sku: draft.sku.trim(),
      barcode: draft.barcode,
      // "" -> null tells the API to inherit the product's default.
      mrp: draft.mrp.trim() || null,
      selling_price: draft.selling_price.trim() || null,
      purchase_price: draft.purchase_price.trim() || null,
      tax_rate: draft.tax_rate.trim() || null,
      is_active: draft.is_active,
      attribute_values: draft.rows
        .filter((r) => r.attribute !== "" && r.value.trim() !== "")
        .map((r) => ({ attribute: r.attribute as number, value: r.value.trim() })),
    };
    try {
      if (editingId === "new") {
        await create.mutateAsync(payload);
      } else if (typeof editingId === "number") {
        await update.mutateAsync({ id: editingId, body: payload });
      }
      cancel();
    } catch (err) {
      if (err instanceof ApiError && err.fields) {
        setFieldErrors(err.fields);
        setFormError(err.message);
      } else {
        setFormError(err instanceof Error ? err.message : "Could not save the variant.");
      }
    }
  };

  const addAttribute = async () => {
    const name = newAttrName.trim();
    if (!name) return;
    const created = await createAttribute.mutateAsync({
      name,
      code: name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, ""),
    });
    setNewAttrName("");
    set("rows", [...draft.rows, { attribute: created.id, value: "" }]);
  };

  const productActive = product.status === "active";
  const statusNotice =
    product.status === "draft"
      ? "This product is a draft — its variants aren’t shown to buyers yet."
      : product.status === "inactive"
        ? "This product is inactive — its variants aren’t shown to buyers."
        : product.status === "discontinued"
          ? "This product is discontinued — all its variants read as discontinued."
          : null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Variants</h2>
        {editingId === null && (
          <Button size="sm" onClick={startNew}>
            Add variant
          </Button>
        )}
      </div>

      {statusNotice && (
        <p className="rounded-md border border-dashed px-3 py-2 text-sm text-muted-foreground">
          {statusNotice}
        </p>
      )}

      {variantsQuery.isPending && (
        <p className="text-sm text-muted-foreground">Loading variants…</p>
      )}

      {!variantsQuery.isPending && variants.length === 0 && editingId === null && (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            No variants yet. Every product needs at least one to be sellable.
          </CardContent>
        </Card>
      )}

      {variants.length > 0 && (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/40 text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-3 py-2 font-medium">SKU</th>
                <th className="px-3 py-2 font-medium">Attributes</th>
                <th className="px-3 py-2 font-medium">Images</th>
                <th className="px-3 py-2 font-medium">Selling (incl. GST)</th>
                <th className="px-3 py-2 font-medium">Base + GST</th>
                <th className="px-3 py-2 font-medium">Discount</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {variants.map((v) => (
                <tr key={v.id} className="border-b last:border-0">
                  <td className="px-3 py-2 font-mono">{v.sku}</td>
                  <td className="px-3 py-2">
                    {v.attribute_values.length === 0
                      ? "—"
                      : v.attribute_values
                          .map((a) => `${a.attribute_name}: ${a.value}`)
                          .join(", ")}
                  </td>
                  <td className="px-3 py-2">
                    <VariantThumbnails
                      images={images.filter((img) => img.variant === v.id)}
                    />
                  </td>
                  <td className="px-3 py-2">
                    ₹{v.effective_selling_price}
                    {v.selling_price === null && (
                      <span className="ml-1 text-xs text-muted-foreground">(inherited)</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">
                    ₹{v.base_price} + ₹{v.gst_amount}
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">
                    {Number(v.discount_amount) > 0
                      ? `₹${v.discount_amount} · ${v.discount_percent}%`
                      : "—"}
                  </td>
                  <td className="px-3 py-2">
                    <StatusBadge status={v.effective_status} />
                    {productActive && !v.is_active && (
                      <span className="ml-1 text-xs text-muted-foreground">(set inactive)</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <div className="flex justify-end gap-2">
                      <Button size="sm" variant="outline" onClick={() => startEdit(v)}>
                        Edit
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          if (confirm(`Delete variant ${v.sku}?`)) remove.mutate(v.id);
                        }}
                      >
                        Delete
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editingId !== null && (
        <Card>
          <CardContent className="space-y-4 py-5">
            <h3 className="font-medium">
              {editingId === "new" ? "New variant" : "Edit variant"}
            </h3>

            {formError && <p className="text-sm text-destructive">{formError}</p>}

            <div className="space-y-2">
              <Label>Attributes (size / colour / material …)</Label>
              {draft.rows.map((row, i) => (
                <div key={i} className="flex flex-wrap items-center gap-2">
                  <select
                    value={row.attribute}
                    onChange={(e) =>
                      updateRow(i, {
                        attribute: e.target.value ? Number(e.target.value) : "",
                      })
                    }
                    className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
                  >
                    <option value="">Select attribute…</option>
                    {attributes.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name}
                      </option>
                    ))}
                  </select>
                  <Input
                    value={row.value}
                    onChange={(e) => updateRow(i, { value: e.target.value })}
                    placeholder="Value, e.g. 11 × 23 inch"
                    className="max-w-xs"
                  />
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => removeRow(i)}
                  >
                    Remove
                  </Button>
                </div>
              ))}
              <div className="flex flex-wrap items-center gap-2">
                <Button type="button" size="sm" variant="outline" onClick={addRow}>
                  Add attribute row
                </Button>
                <span className="text-xs text-muted-foreground">or define a new attribute:</span>
                <Input
                  value={newAttrName}
                  onChange={(e) => setNewAttrName(e.target.value)}
                  placeholder="New attribute name"
                  className="max-w-[12rem]"
                />
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={addAttribute}
                  disabled={!newAttrName.trim() || createAttribute.isPending}
                >
                  Add
                </Button>
              </div>
              {fieldErrors.attribute_values && (
                <p className="text-xs text-destructive">
                  {fieldErrors.attribute_values.join(" ")}
                </p>
              )}
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label>Display name (optional)</Label>
                <Input
                  value={draft.name}
                  onChange={(e) => set("name", e.target.value)}
                  placeholder="e.g. 11 × 23 inch"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Variant code (for SKU)</Label>
                <Input
                  value={draft.code}
                  onChange={(e) => set("code", e.target.value)}
                  placeholder="e.g. 11X23"
                />
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label>SKU</Label>
              <SkuField
                value={draft.sku}
                onChange={(sku) => set("sku", sku)}
                excludeVariantId={typeof editingId === "number" ? editingId : undefined}
                suggestContext={{
                  product: product.id,
                  category: product.category,
                  variant_code: draft.code,
                  attribute_values: draft.rows.map((r) => r.value).filter(Boolean),
                }}
              />
              {fieldErrors.sku && (
                <p className="text-xs text-destructive">{fieldErrors.sku.join(" ")}</p>
              )}
              <p className="text-xs text-muted-foreground">
                Leave blank to let the server assign one on save.
              </p>
            </div>

            <div className="space-y-1.5">
              <Label>Pricing</Label>
              <p className="text-xs text-muted-foreground">
                Leave a field blank to inherit the product’s default. Discount is derived from
                MRP and selling price.
              </p>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {PRICE_KEYS.map((key) => {
                  const inherited = draft[key].trim() === "" && productDefault(key) !== "";
                  return (
                    <div key={key} className="flex flex-col gap-1.5">
                      <Label>{PRICE_LABELS[key]}</Label>
                      <Input
                        type="number"
                        step="0.01"
                        min="0"
                        value={draft[key]}
                        placeholder={
                          productDefault(key) !== "" ? `Inherits ₹${productDefault(key)}` : "—"
                        }
                        onChange={(e) => set(key, e.target.value)}
                      />
                      {inherited && (
                        <p className="text-xs text-muted-foreground">
                          Inheriting ₹{productDefault(key)} from the product.
                        </p>
                      )}
                      {fieldErrors[key] && (
                        <p className="text-xs text-destructive">{fieldErrors[key].join(" ")}</p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {preview && (
              <p className="rounded-md bg-muted/50 px-3 py-2 text-sm text-muted-foreground">
                Taxable base <strong>₹{preview.base}</strong> + GST{" "}
                <strong>₹{preview.gst}</strong> = ₹{preview.total}{" "}
                <span className="text-xs">(effective values; server recalculates on save)</span>
              </p>
            )}

            <div className="space-y-1">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={draft.is_active}
                  disabled={!productActive}
                  onChange={(e) => set("is_active", e.target.checked)}
                />
                Variant active (available for sale)
              </label>
              {!productActive && (
                <p className="text-xs text-muted-foreground">
                  Availability is controlled by the product status while the product is{" "}
                  <strong>{product.status}</strong>. Set the product to <strong>Active</strong>{" "}
                  to toggle this per variant.
                </p>
              )}
            </div>

            <div className="flex gap-2">
              <Button onClick={submit} disabled={create.isPending || update.isPending}>
                {create.isPending || update.isPending ? "Saving…" : "Save variant"}
              </Button>
              <Button variant="outline" onClick={cancel}>
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
