import { useMemo, useRef, useState } from "react";

import { ApiError } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useImageMutations, useImages } from "./hooks";
import type { Product, ProductImage, ProductVariant } from "./types";

/** "" means the image belongs to the whole product, not a single variant. */
type Scope = "" | number;

function variantLabel(v: ProductVariant): string {
  return v.name ? `${v.sku} · ${v.name}` : v.sku;
}

export function ImageUploader({ product }: { product: Product }) {
  const variants = useMemo(() => product.variants ?? [], [product.variants]);
  const imagesQuery = useImages(product.id);
  const { upload, update, remove } = useImageMutations(product.id);
  const inputRef = useRef<HTMLInputElement>(null);
  const [scope, setScope] = useState<Scope>("");
  const [error, setError] = useState<string | null>(null);

  const images = useMemo(() => imagesQuery.data?.data ?? [], [imagesQuery.data]);

  const groups = useMemo(() => {
    const productLevel = images.filter((i) => i.variant === null);
    const byVariant = variants
      .map((v) => ({
        key: v.id as Scope,
        label: variantLabel(v),
        images: images.filter((i) => i.variant === v.id),
      }))
      .filter((g) => g.images.length > 0);
    const orphaned = images.filter(
      (i) => i.variant !== null && !variants.some((v) => v.id === i.variant),
    );
    return [
      { key: "" as Scope, label: "Whole product", images: productLevel },
      ...byVariant,
      ...(orphaned.length
        ? [{ key: "orphan" as const, label: "Other variant", images: orphaned }]
        : []),
    ];
  }, [images, variants]);

  const onPick = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setError(null);
    const productLevelCount = images.filter((i) => i.variant === null).length;
    try {
      for (const [idx, file] of Array.from(files).entries()) {
        await upload.mutateAsync({
          product: product.id,
          variant: scope === "" ? null : scope,
          image: file,
          is_primary: scope === "" && productLevelCount === 0 && idx === 0,
        });
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed.");
    } finally {
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Images</h2>
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-xs text-muted-foreground">Attach to</label>
          <select
            value={scope}
            onChange={(e) => setScope(e.target.value === "" ? "" : Number(e.target.value))}
            className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
          >
            <option value="">Whole product</option>
            {variants.map((v) => (
              <option key={v.id} value={v.id}>
                {variantLabel(v)}
              </option>
            ))}
          </select>
          <input
            ref={inputRef}
            type="file"
            accept="image/*"
            multiple
            hidden
            onChange={(e) => onPick(e.target.files)}
          />
          <Button
            size="sm"
            onClick={() => inputRef.current?.click()}
            disabled={upload.isPending}
          >
            {upload.isPending ? "Uploading…" : "Upload images"}
          </Button>
        </div>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {imagesQuery.isPending && (
        <p className="text-sm text-muted-foreground">Loading images…</p>
      )}

      {!imagesQuery.isPending && images.length === 0 && (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            No images yet.
          </CardContent>
        </Card>
      )}

      {images.length > 0 &&
        groups
          .filter((g) => g.images.length > 0)
          .map((group) => (
            <div key={String(group.key)} className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {group.label}
                </span>
                <Badge variant="muted">{group.images.length}</Badge>
              </div>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
                {group.images.map((img) => (
                  <ImageCard
                    key={img.id}
                    image={img}
                    productName={product.name}
                    variants={variants}
                    onMakePrimary={() =>
                      update.mutate({ id: img.id, body: { is_primary: true } })
                    }
                    onMove={(value) =>
                      update.mutate({
                        id: img.id,
                        body: { variant: value === "" ? null : value },
                      })
                    }
                    onDelete={() => {
                      if (confirm("Delete this image?")) remove.mutate(img.id);
                    }}
                  />
                ))}
              </div>
            </div>
          ))}
    </div>
  );
}

function ImageCard({
  image,
  productName,
  variants,
  onMakePrimary,
  onMove,
  onDelete,
}: {
  image: ProductImage;
  productName: string;
  variants: ProductVariant[];
  onMakePrimary: () => void;
  onMove: (value: Scope) => void;
  onDelete: () => void;
}) {
  return (
    <div className="overflow-hidden rounded-md border">
      <div className="aspect-square bg-muted">
        {image.image_url && (
          <img
            src={image.image_url}
            alt={image.alt_text || productName}
            className="h-full w-full object-cover"
          />
        )}
      </div>
      <div className="space-y-1.5 p-2 text-xs">
        <div className="flex items-center justify-between gap-1">
          {image.is_primary ? (
            <span className="font-medium text-primary">Primary</span>
          ) : (
            <button
              type="button"
              className="text-muted-foreground hover:text-foreground"
              onClick={onMakePrimary}
            >
              Make primary
            </button>
          )}
          <button
            type="button"
            className="text-muted-foreground hover:text-destructive"
            onClick={onDelete}
          >
            Delete
          </button>
        </div>
        <select
          value={image.variant ?? ""}
          onChange={(e) => onMove(e.target.value === "" ? "" : Number(e.target.value))}
          className="h-7 w-full rounded border border-input bg-transparent px-1 text-xs"
          title="Move this image to another scope"
        >
          <option value="">Whole product</option>
          {variants.map((v) => (
            <option key={v.id} value={v.id}>
              {variantLabel(v)}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
