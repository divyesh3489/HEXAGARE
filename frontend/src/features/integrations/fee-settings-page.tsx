import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { ApiError } from "@/api/client";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAllCategories } from "@/features/products/hooks";
import { productsApi } from "@/features/products/api";
import { useSalesChannels } from "@/features/sales/hooks";
import { useHasPermission } from "@/hooks/use-auth";
import { useFeeConfigMutations, useFeeConfigs } from "./hooks";
import { AMAZON_FEE_NAMES, AMAZON_FEE_TYPES, type AmazonFeeConfig, type AmazonFeeName, type AmazonFeeType } from "./types";

const selectClass =
  "h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

const FEE_NAME_LABELS: Record<AmazonFeeName, string> = {
  REFERRAL: "Referral fee",
  CLOSING: "Closing fee",
  FULFILLMENT: "Fulfillment fee",
  SHIPPING: "Shipping / courier",
  ADVERTISING: "Advertising",
  OTHER: "Other charges",
};

interface Draft {
  fee_name: AmazonFeeName;
  fee_type: AmazonFeeType;
  value: string;
  scope: "" | "category" | "product";
  applicable_category: string;
  applicable_product: string;
  effective_from: string;
  effective_to: string;
}

const EMPTY: Draft = {
  fee_name: "REFERRAL",
  fee_type: "PERCENTAGE",
  value: "",
  scope: "",
  applicable_category: "",
  applicable_product: "",
  effective_from: new Date().toISOString().slice(0, 10),
  effective_to: "",
};

function useDebounced(value: string, delay = 300): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const handle = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(handle);
  }, [value, delay]);
  return debounced;
}

function ProductPicker({
  value,
  onChange,
}: {
  value: { id: number; label: string } | null;
  onChange: (product: { id: number; label: string } | null) => void;
}) {
  const [text, setText] = useState("");
  const debounced = useDebounced(text);
  const { data, isFetching } = useQuery({
    queryKey: ["integrations", "amazon", "product-search", debounced],
    queryFn: () => productsApi.list({ search: debounced, page_size: 10 }),
    enabled: debounced.trim().length >= 2,
  });
  const results = data?.data ?? [];

  if (value) {
    return (
      <div className="flex items-center gap-2">
        <Badge variant="secondary">{value.label}</Badge>
        <Button size="sm" variant="ghost" onClick={() => onChange(null)}>
          Change
        </Button>
      </div>
    );
  }

  return (
    <div className="relative">
      <Input
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Search a product…"
        autoComplete="off"
      />
      {debounced.trim().length >= 2 && (
        <Card className="absolute z-10 mt-1 max-h-56 w-full overflow-y-auto py-1">
          {isFetching && <p className="px-3 py-2 text-xs text-muted-foreground">Searching…</p>}
          {!isFetching && results.length === 0 && (
            <p className="px-3 py-2 text-xs text-muted-foreground">No products match.</p>
          )}
          {results.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => {
                onChange({ id: p.id, label: p.name });
                setText("");
              }}
              className="flex w-full items-center px-3 py-2 text-left text-sm hover:bg-muted"
            >
              {p.name}
            </button>
          ))}
        </Card>
      )}
    </div>
  );
}

export function AmazonFeeSettingsPage() {
  const canManage = useHasPermission()("integrations.amazon");
  const { data, isPending, error } = useFeeConfigs();
  const { data: channels } = useSalesChannels();
  const { data: categories } = useAllCategories();
  const { create, update, remove } = useFeeConfigMutations();
  const configs = data?.data ?? [];

  const amazonChannel = channels?.data.find((c) => c.code === "AMAZON") ?? channels?.data[0];

  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [product, setProduct] = useState<{ id: number; label: string } | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const startNew = () => {
    setDraft(EMPTY);
    setProduct(null);
    setAdding(true);
    setFormError(null);
  };
  const cancel = () => setAdding(false);

  const submit = async () => {
    setFormError(null);
    if (!amazonChannel) {
      setFormError("No sales channel available yet.");
      return;
    }
    if (!draft.value.trim() || !draft.effective_from) {
      setFormError("Value and effective-from date are required.");
      return;
    }
    try {
      await create.mutateAsync({
        fee_name: draft.fee_name,
        fee_type: draft.fee_type,
        value: draft.value,
        sales_channel: amazonChannel.id,
        applicable_category:
          draft.scope === "category" && draft.applicable_category
            ? Number(draft.applicable_category)
            : null,
        applicable_product: draft.scope === "product" && product ? product.id : null,
        effective_from: draft.effective_from,
        effective_to: draft.effective_to || null,
      });
      cancel();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.detail : "Could not save the fee rule.");
    }
  };

  const toggleActive = (config: AmazonFeeConfig) =>
    update.mutate({ id: config.id, body: { is_active: !config.is_active } });

  return (
    <div>
      <PageHeader
        title="Amazon fee settings"
        description="Fallback fee rates used only when a CSV row leaves that fee column blank -- an actual figure from the import always wins."
        actions={canManage && !adding ? <Button onClick={startNew}>New fee rule</Button> : undefined}
      />

      {adding && (
        <Card className="mb-4">
          <CardContent className="space-y-4 py-5">
            {formError && <p className="text-sm text-destructive">{formError}</p>}
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label>Fee</Label>
                <select
                  className={selectClass}
                  value={draft.fee_name}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, fee_name: e.target.value as AmazonFeeName }))
                  }
                >
                  {AMAZON_FEE_NAMES.map((name) => (
                    <option key={name} value={name}>
                      {FEE_NAME_LABELS[name]}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Type</Label>
                <select
                  className={selectClass}
                  value={draft.fee_type}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, fee_type: e.target.value as AmazonFeeType }))
                  }
                >
                  {AMAZON_FEE_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {type === "PERCENTAGE" ? "Percentage of taxable value" : "Fixed amount"}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>{draft.fee_type === "PERCENTAGE" ? "Percentage (0-100)" : "Amount (₹)"}</Label>
                <Input
                  value={draft.value}
                  onChange={(e) => setDraft((d) => ({ ...d, value: e.target.value }))}
                  inputMode="decimal"
                  placeholder={draft.fee_type === "PERCENTAGE" ? "15.00" : "80.00"}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Applies to</Label>
                <select
                  className={selectClass}
                  value={draft.scope}
                  onChange={(e) => {
                    setProduct(null);
                    setDraft((d) => ({
                      ...d,
                      scope: e.target.value as Draft["scope"],
                      applicable_category: "",
                    }));
                  }}
                >
                  <option value="">Every product (channel-wide)</option>
                  <option value="category">One category</option>
                  <option value="product">One product</option>
                </select>
              </div>
              {draft.scope === "category" && (
                <div className="flex flex-col gap-1.5">
                  <Label>Category</Label>
                  <select
                    className={selectClass}
                    value={draft.applicable_category}
                    onChange={(e) =>
                      setDraft((d) => ({ ...d, applicable_category: e.target.value }))
                    }
                  >
                    <option value="">— Select —</option>
                    {(categories?.data ?? []).map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              {draft.scope === "product" && (
                <div className="flex flex-col gap-1.5">
                  <Label>Product</Label>
                  <ProductPicker value={product} onChange={setProduct} />
                </div>
              )}
              <div className="flex flex-col gap-1.5">
                <Label>Effective from</Label>
                <input
                  type="date"
                  className={selectClass}
                  value={draft.effective_from}
                  onChange={(e) => setDraft((d) => ({ ...d, effective_from: e.target.value }))}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Effective to (blank = open-ended)</Label>
                <input
                  type="date"
                  className={selectClass}
                  value={draft.effective_to}
                  onChange={(e) => setDraft((d) => ({ ...d, effective_to: e.target.value }))}
                />
              </div>
            </div>
            <div className="flex gap-2">
              <Button onClick={submit} disabled={create.isPending}>
                Save
              </Button>
              <Button variant="outline" onClick={cancel}>
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {error && <p className="text-sm text-destructive">Couldn&apos;t load fee settings.</p>}

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Fee</th>
                  <th className="px-4 py-3 font-medium">Value</th>
                  <th className="px-4 py-3 font-medium">Applies to</th>
                  <th className="px-4 py-3 font-medium">Effective</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  {canManage && <th className="px-4 py-3" />}
                </tr>
              </thead>
              <tbody>
                {isPending && (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                      Loading…
                    </td>
                  </tr>
                )}
                {!isPending && configs.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-12 text-center text-muted-foreground">
                      No fee rules configured -- blank CSV fee columns import as ₹0.00 until you
                      add one.
                    </td>
                  </tr>
                )}
                {configs.map((c) => (
                  <tr key={c.id} className="border-b last:border-0">
                    <td className="px-4 py-3">{FEE_NAME_LABELS[c.fee_name]}</td>
                    <td className="px-4 py-3">
                      {c.fee_type === "PERCENTAGE" ? `${c.value}%` : `₹${c.value}`}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {c.applicable_product_name ??
                        c.applicable_category_name ??
                        "Every product"}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {c.effective_from} → {c.effective_to ?? "open"}
                    </td>
                    <td className="px-4 py-3">
                      {c.is_active ? <Badge>Active</Badge> : <Badge variant="muted">Inactive</Badge>}
                    </td>
                    {canManage && (
                      <td className="px-4 py-3 text-right">
                        <div className="flex justify-end gap-2">
                          <Button size="sm" variant="outline" onClick={() => toggleActive(c)}>
                            {c.is_active ? "Deactivate" : "Activate"}
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => {
                              if (confirm("Delete this fee rule?")) remove.mutate(c.id);
                            }}
                          >
                            Delete
                          </Button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
