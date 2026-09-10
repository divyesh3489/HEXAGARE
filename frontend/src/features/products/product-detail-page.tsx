import type { ReactNode } from "react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useHasPermission } from "@/hooks/use-auth";
import { useProduct, useProductMutations } from "./hooks";
import { ImageUploader } from "./image-uploader";
import { ProductForm } from "./product-form";
import { VariantManager } from "./variant-manager";

export function ProductDetailPage() {
  const params = useParams();
  const navigate = useNavigate();
  const productId = Number(params.productId);
  const canManage = useHasPermission()("products.manage");

  const { data: product, isPending, error } = useProduct(
    Number.isNaN(productId) ? undefined : productId,
  );
  const { update, remove } = useProductMutations();
  const [editing, setEditing] = useState(false);

  if (isPending) {
    return (
      <div>
        <PageHeader title="Product" />
        <p className="text-sm text-muted-foreground">Loading…</p>
      </div>
    );
  }

  if (error || !product) {
    return (
      <div>
        <PageHeader title="Product" />
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            This product could not be loaded.
            <div className="mt-3">
              <Button variant="outline" size="sm" onClick={() => navigate("/products")}>
                Back to products
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <PageHeader
          title={product.name}
          description={`${product.category_name}${product.brand ? ` · ${product.brand}` : ""}`}
          actions={
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => navigate("/products")}>
                Back
              </Button>
              {canManage && !editing && (
                <Button size="sm" onClick={() => setEditing(true)}>
                  Edit details
                </Button>
              )}
              {canManage && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={async () => {
                    if (confirm(`Delete “${product.name}”? This removes its variants too.`)) {
                      await remove.mutateAsync(product.id);
                      navigate("/products");
                    }
                  }}
                >
                  Delete
                </Button>
              )}
            </div>
          }
        />

        {editing ? (
          <Card>
            <CardContent className="py-6">
              <ProductForm
                product={product}
                onCancel={() => setEditing(false)}
                onSubmit={async (body) => {
                  await update.mutateAsync({ id: product.id, body });
                  setEditing(false);
                }}
              />
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardContent className="grid gap-x-8 gap-y-2 py-5 text-sm sm:grid-cols-2">
              <Detail label="Status">
                <Badge variant={product.status === "active" ? "default" : "muted"}>
                  {product.status}
                </Badge>
              </Detail>
              <Detail label="Product code">{product.code || "—"}</Detail>
              <Detail label="HSN / SAC">{product.hsn_sac || "—"}</Detail>
              <Detail label="Weight">{product.weight ? `${product.weight} kg` : "—"}</Detail>
              <Detail label="Dimensions">{product.dimensions || "—"}</Detail>
              <Detail label="Tags">
                {product.tags.length ? product.tags.join(", ") : "—"}
              </Detail>
              <Detail label="Default MRP">
                {product.mrp ? `₹${product.mrp}` : "—"}
              </Detail>
              <Detail label="Default selling price (incl. GST)">
                {product.selling_price ? `₹${product.selling_price}` : "—"}
              </Detail>
              <Detail label="Default purchase price">
                {product.purchase_price ? `₹${product.purchase_price}` : "—"}
              </Detail>
              <Detail label="Default GST rate">
                {product.tax_rate ? `${product.tax_rate}%` : "—"}
              </Detail>
              <Detail label="Default discount">
                {Number(product.discount_amount) > 0
                  ? `₹${product.discount_amount} (${product.discount_percent}%)`
                  : "—"}
              </Detail>
              {product.description && (
                <Detail label="Description" full>
                  {product.description}
                </Detail>
              )}
              {product.notes && (
                <Detail label="Notes" full>
                  {product.notes}
                </Detail>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      <VariantManager product={product} />
      <ImageUploader product={product} />
    </div>
  );
}

function Detail({
  label,
  children,
  full,
}: {
  label: string;
  children: ReactNode;
  full?: boolean;
}) {
  return (
    <div className={full ? "sm:col-span-2" : undefined}>
      <span className="text-xs uppercase tracking-wider text-muted-foreground">{label}</span>
      <div className="mt-0.5">{children}</div>
    </div>
  );
}
