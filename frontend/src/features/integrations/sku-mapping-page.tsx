import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { ApiError } from "@/api/client";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { variantsApi } from "@/features/products/api";
import { useHasPermission } from "@/hooks/use-auth";
import { useSkuMappingMutations, useSkuMappings } from "./hooks";
import type { AmazonSkuMapping } from "./types";

function useDebounced(value: string, delay = 300): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const handle = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(handle);
  }, [value, delay]);
  return debounced;
}

function VariantPicker({
  value,
  onChange,
}: {
  value: { id: number; label: string } | null;
  onChange: (variant: { id: number; label: string } | null) => void;
}) {
  const [text, setText] = useState("");
  const debounced = useDebounced(text);
  const { data, isFetching } = useQuery({
    queryKey: ["integrations", "amazon", "variant-search", debounced],
    queryFn: () => variantsApi.search(debounced),
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
        placeholder="Search Hexagare product by name or SKU…"
        autoComplete="off"
      />
      {debounced.trim().length >= 2 && (
        <Card className="absolute z-10 mt-1 max-h-56 w-full overflow-y-auto py-1">
          {isFetching && <p className="px-3 py-2 text-xs text-muted-foreground">Searching…</p>}
          {!isFetching && results.length === 0 && (
            <p className="px-3 py-2 text-xs text-muted-foreground">No variants match.</p>
          )}
          {results.map((v) => (
            <button
              key={v.id}
              type="button"
              onClick={() => {
                onChange({ id: v.id, label: v.name ? `${v.sku} — ${v.name}` : v.sku });
                setText("");
              }}
              className="flex w-full items-center px-3 py-2 text-left text-sm hover:bg-muted"
            >
              <span className="font-mono text-xs text-muted-foreground">{v.sku}</span>
              {v.name ? <span className="ml-2">{v.name}</span> : null}
            </button>
          ))}
        </Card>
      )}
    </div>
  );
}

export function AmazonSkuMappingPage() {
  const canManage = useHasPermission()("integrations.amazon");
  const { data, isPending, error } = useSkuMappings();
  const { create, update, remove } = useSkuMappingMutations();
  const mappings = data?.data ?? [];

  const [adding, setAdding] = useState(false);
  const [amazonSku, setAmazonSku] = useState("");
  const [variant, setVariant] = useState<{ id: number; label: string } | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const startNew = () => {
    setAdding(true);
    setAmazonSku("");
    setVariant(null);
    setFormError(null);
  };
  const cancel = () => setAdding(false);

  const submit = async () => {
    setFormError(null);
    if (!amazonSku.trim() || !variant) {
      setFormError("Enter an Amazon SKU and pick a Hexagare variant.");
      return;
    }
    try {
      await create.mutateAsync({ amazon_sku: amazonSku.trim(), variant: variant.id });
      cancel();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.detail : "Could not save the mapping.");
    }
  };

  const toggleActive = (mapping: AmazonSkuMapping) =>
    update.mutate({ id: mapping.id, body: { is_active: !mapping.is_active } });

  return (
    <div>
      <PageHeader
        title="Amazon SKU mapping"
        description="Amazon SKU ↔ Hexagare variant. The importer auto-creates a mapping only when the Amazon SKU matches a Hexagare SKU exactly -- anything else needs a row here."
        actions={
          canManage && !adding ? <Button onClick={startNew}>New mapping</Button> : undefined
        }
      />

      {adding && (
        <Card className="mb-4">
          <CardContent className="space-y-4 py-5">
            {formError && <p className="text-sm text-destructive">{formError}</p>}
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label>Amazon SKU</Label>
                <Input
                  value={amazonSku}
                  onChange={(e) => setAmazonSku(e.target.value)}
                  placeholder="e.g. AMZ-DM-BLACK"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Hexagare variant</Label>
                <VariantPicker value={variant} onChange={setVariant} />
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

      {error && <p className="text-sm text-destructive">Couldn&apos;t load SKU mappings.</p>}

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Amazon SKU</th>
                  <th className="px-4 py-3 font-medium">Hexagare variant</th>
                  <th className="px-4 py-3 font-medium">Product</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  {canManage && <th className="px-4 py-3" />}
                </tr>
              </thead>
              <tbody>
                {isPending && (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                      Loading…
                    </td>
                  </tr>
                )}
                {!isPending && mappings.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-12 text-center text-muted-foreground">
                      No mappings yet -- unmapped Amazon SKUs fail the order at import time.
                    </td>
                  </tr>
                )}
                {mappings.map((m) => (
                  <tr key={m.id} className="border-b last:border-0">
                    <td className="px-4 py-3 font-mono">{m.amazon_sku}</td>
                    <td className="px-4 py-3 font-mono text-muted-foreground">{m.variant_sku}</td>
                    <td className="px-4 py-3">{m.product_name}</td>
                    <td className="px-4 py-3">
                      {m.is_active ? <Badge>Active</Badge> : <Badge variant="muted">Inactive</Badge>}
                    </td>
                    {canManage && (
                      <td className="px-4 py-3 text-right">
                        <div className="flex justify-end gap-2">
                          <Button size="sm" variant="outline" onClick={() => toggleActive(m)}>
                            {m.is_active ? "Deactivate" : "Activate"}
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => {
                              if (confirm(`Delete mapping for "${m.amazon_sku}"?`))
                                remove.mutate(m.id);
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
