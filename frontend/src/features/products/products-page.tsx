import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useHasPermission } from "@/hooks/use-auth";
import { useAllCategories, useProductMutations, useProducts } from "./hooks";
import { ProductForm } from "./product-form";
import { PRODUCT_STATUSES, type ProductStatus } from "./types";

const PAGE_SIZE = 20;

function priceRange(min: string | null, max: string | null): string {
  if (!min && !max) return "—";
  if (min === max) return `₹${min}`;
  return `₹${min} – ₹${max}`;
}

export function ProductsPage() {
  const navigate = useNavigate();
  const canManage = useHasPermission()("products.manage");

  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState<ProductStatus | "">("");
  const [creating, setCreating] = useState(false);

  const categoriesQuery = useAllCategories();
  const { data, isPending, isFetching, error } = useProducts({
    page,
    page_size: PAGE_SIZE,
    search,
    category,
    status,
  });
  const { create } = useProductMutations();

  const products = data?.data ?? [];
  const count = data?.meta.count ?? 0;

  if (creating) {
    return (
      <div>
        <PageHeader title="New product" />
        <Card>
          <CardContent className="py-6">
            <ProductForm
              onCancel={() => setCreating(false)}
              onSubmit={async (body) => {
                const product = await create.mutateAsync(body);
                setCreating(false);
                navigate(`/products/${product.id}`);
              }}
              submitLabel="Create product"
            />
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Products"
        description="Your catalog. Open a product to manage its variants and images."
        actions={
          canManage ? <Button onClick={() => setCreating(true)}>New product</Button> : undefined
        }
      />

      <div className="mb-4 flex flex-wrap gap-2">
        <Input
          placeholder="Search name, brand or SKU…"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          className="max-w-xs"
        />
        <select
          value={category}
          onChange={(e) => {
            setCategory(e.target.value);
            setPage(1);
          }}
          className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
        >
          <option value="">All categories</option>
          {(categoriesQuery.data?.data ?? []).map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as ProductStatus | "");
            setPage(1);
          }}
          className="h-9 rounded-md border border-input bg-transparent px-3 text-sm capitalize"
        >
          <option value="">All statuses</option>
          {PRODUCT_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {error && <p className="text-sm text-destructive">Couldn’t load products.</p>}

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Product</th>
                  <th className="px-4 py-3 font-medium">Category</th>
                  <th className="px-4 py-3 font-medium">Brand</th>
                  <th className="px-4 py-3 font-medium">Variants</th>
                  <th className="px-4 py-3 font-medium">Price</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {isPending &&
                  Array.from({ length: 6 }).map((_, i) => (
                    <tr key={i} className="border-b">
                      {Array.from({ length: 6 }).map((__, j) => (
                        <td key={j} className="px-4 py-3">
                          <Skeleton className="h-4 w-24" />
                        </td>
                      ))}
                    </tr>
                  ))}

                {!isPending && products.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-12 text-center text-muted-foreground">
                      No products{search || category || status ? " match these filters" : " yet"}.
                    </td>
                  </tr>
                )}

                {products.map((p) => (
                  <tr
                    key={p.id}
                    className="cursor-pointer border-b last:border-0 hover:bg-accent/50"
                    onClick={() => navigate(`/products/${p.id}`)}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <div className="size-9 shrink-0 overflow-hidden rounded bg-muted">
                          {p.primary_image_url && (
                            <img
                              src={p.primary_image_url}
                              alt=""
                              className="h-full w-full object-cover"
                            />
                          )}
                        </div>
                        <span className="font-medium">{p.name}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{p.category_name}</td>
                    <td className="px-4 py-3 text-muted-foreground">{p.brand || "—"}</td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {p.variant_count}
                      {p.status === "active" && (
                        <span className="ml-1 text-xs">· {p.available_variant_count} live</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {priceRange(p.price_min, p.price_max)}
                    </td>
                    <td className="px-4 py-3 capitalize">
                      <Badge variant={p.status === "active" ? "default" : "muted"}>
                        {p.status}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {count > PAGE_SIZE && (
        <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground">
          <span>
            {count} product{count === 1 ? "" : "s"}
            {isFetching ? " · updating…" : ""}
          </span>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={!data?.meta.previous}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Previous
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!data?.meta.next}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
