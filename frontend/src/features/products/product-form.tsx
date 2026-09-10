import type { ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useAllCategories } from "./hooks";
import { PRODUCT_STATUSES, type Product } from "./types";

const schema = z.object({
  name: z.string().min(1, "Name is required"),
  code: z.string().optional(),
  category: z.string().min(1, "Choose a category"),
  brand: z.string().optional(),
  status: z.enum(PRODUCT_STATUSES),
  hsn_sac: z.string().optional(),
  weight: z.string().optional(),
  dimensions: z.string().optional(),
  tags: z.string().optional(),
  description: z.string().optional(),
  notes: z.string().optional(),
  mrp: z.string().optional(),
  selling_price: z.string().optional(),
  purchase_price: z.string().optional(),
  tax_rate: z.string().optional(),
});

type FormValues = z.infer<typeof schema>;

export interface ProductFormProps {
  product?: Product;
  onSubmit: (body: Partial<Product>) => Promise<unknown>;
  onCancel: () => void;
  submitLabel?: string;
}

export function ProductForm({ product, onSubmit, onCancel, submitLabel }: ProductFormProps) {
  const categoriesQuery = useAllCategories();
  const categories = categoriesQuery.data?.data ?? [];

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: product?.name ?? "",
      code: product?.code ?? "",
      category: product ? String(product.category) : "",
      brand: product?.brand ?? "",
      status: product?.status ?? "draft",
      hsn_sac: product?.hsn_sac ?? "",
      weight: product?.weight ?? "",
      dimensions: product?.dimensions ?? "",
      tags: (product?.tags ?? []).join(", "),
      description: product?.description ?? "",
      notes: product?.notes ?? "",
      mrp: product?.mrp ?? "",
      selling_price: product?.selling_price ?? "",
      purchase_price: product?.purchase_price ?? "",
      tax_rate: product?.tax_rate ?? "",
    },
  });

  const submit = handleSubmit(async (values) => {
    const body: Partial<Product> = {
      name: values.name,
      code: values.code ?? "",
      category: Number(values.category),
      brand: values.brand ?? "",
      status: values.status,
      hsn_sac: values.hsn_sac ?? "",
      weight: values.weight ? values.weight : null,
      dimensions: values.dimensions ?? "",
      tags: (values.tags ?? "")
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
      description: values.description ?? "",
      notes: values.notes ?? "",
      mrp: values.mrp?.trim() ? values.mrp.trim() : null,
      selling_price: values.selling_price?.trim() ? values.selling_price.trim() : null,
      purchase_price: values.purchase_price?.trim() ? values.purchase_price.trim() : null,
      tax_rate: values.tax_rate?.trim() ? values.tax_rate.trim() : null,
    };
    try {
      await onSubmit(body);
    } catch (err) {
      if (err instanceof ApiError && err.fields) {
        for (const [field, messages] of Object.entries(err.fields)) {
          if (field in schema.shape) {
            setError(field as keyof FormValues, { message: messages[0] });
          }
        }
      }
      throw err;
    }
  });

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Name" error={errors.name?.message}>
          <Input {...register("name")} autoFocus />
        </Field>
        <Field label="Product code (for SKUs)" error={errors.code?.message}>
          <Input {...register("code")} placeholder="e.g. MP" className="font-mono" />
        </Field>
        <Field label="Category" error={errors.category?.message}>
          <select
            {...register("category")}
            className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
          >
            <option value="">Select…</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Brand" error={errors.brand?.message}>
          <Input {...register("brand")} />
        </Field>
        <Field label="Status" error={errors.status?.message}>
          <select
            {...register("status")}
            className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm capitalize"
          >
            {PRODUCT_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </Field>
        <Field label="HSN / SAC" error={errors.hsn_sac?.message}>
          <Input {...register("hsn_sac")} />
        </Field>
        <Field label="Weight (kg)" error={errors.weight?.message}>
          <Input type="number" step="0.001" min="0" {...register("weight")} />
        </Field>
        <Field label="Dimensions" error={errors.dimensions?.message}>
          <Input {...register("dimensions")} placeholder="30 × 25 × 4 cm" />
        </Field>
      </div>

      <Field label="Tags (comma-separated)" error={errors.tags?.message}>
        <Input {...register("tags")} placeholder="gaming, large, rgb" />
      </Field>
      <Field label="Description" error={errors.description?.message}>
        <Textarea {...register("description")} />
      </Field>
      <Field label="Notes" error={errors.notes?.message}>
        <Textarea {...register("notes")} />
      </Field>

      <div className="space-y-1.5 rounded-md border p-4">
        <p className="text-sm font-medium">Default pricing</p>
        <p className="text-xs text-muted-foreground">
          Optional. Variants inherit these unless they set their own. Discount is derived from
          MRP and selling price.
        </p>
        <div className="grid gap-4 pt-2 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="MRP" error={errors.mrp?.message}>
            <Input type="number" step="0.01" min="0" {...register("mrp")} />
          </Field>
          <Field
            label="Selling price (incl. GST)"
            error={errors.selling_price?.message}
          >
            <Input type="number" step="0.01" min="0" {...register("selling_price")} />
          </Field>
          <Field label="Purchase price" error={errors.purchase_price?.message}>
            <Input type="number" step="0.01" min="0" {...register("purchase_price")} />
          </Field>
          <Field label="GST rate (%)" error={errors.tax_rate?.message}>
            <Input type="number" step="0.01" min="0" {...register("tax_rate")} />
          </Field>
        </div>
        {product && Number(product.discount_amount) > 0 && (
          <p className="pt-1 text-xs text-muted-foreground">
            Current discount: ₹{product.discount_amount} ({product.discount_percent}%)
          </p>
        )}
      </div>

      <div className="flex gap-2">
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Saving…" : (submitLabel ?? "Save product")}
        </Button>
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label>{label}</Label>
      {children}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
