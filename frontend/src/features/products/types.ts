export const PRODUCT_STATUSES = [
  "active",
  "inactive",
  "draft",
  "discontinued",
] as const;
export type ProductStatus = (typeof PRODUCT_STATUSES)[number];

export interface Category {
  id: number;
  name: string;
  slug: string;
  code: string;
  parent: number | null;
  parent_name: string | null;
  description: string;
  is_active: boolean;
  product_count: number;
  created_at: string;
  updated_at: string;
}

export interface ProductAttribute {
  id: number;
  name: string;
  code: string;
  is_active: boolean;
}

export interface ProductAttributeValue {
  id?: number;
  attribute: number;
  attribute_name?: string;
  value: string;
}

export interface ProductVariant {
  id: number;
  product: number;
  name: string;
  code: string;
  sku: string;
  barcode: string;
  // nullable overrides — null means "inherit the product default"
  mrp: string | null;
  selling_price: string | null;
  purchase_price: string | null;
  tax_rate: string | null;
  is_active: boolean;
  attribute_values: ProductAttributeValue[];
  // derived, read-only
  effective_mrp: string;
  effective_selling_price: string;
  effective_purchase_price: string;
  effective_tax_rate: string;
  base_price: string;
  gst_amount: string;
  cgst_amount: string;
  sgst_amount: string;
  discount_amount: string;
  discount_percent: string;
  // availability follows the product's status (ADR-006)
  effective_status: ProductStatus;
  is_available: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProductImage {
  id: number;
  product: number;
  variant: number | null;
  image_url: string | null;
  alt_text: string;
  is_primary: boolean;
  sort_order: number;
  created_at: string;
}

export interface ProductListItem {
  id: number;
  name: string;
  code: string;
  category: number;
  category_name: string;
  brand: string;
  status: ProductStatus;
  variant_count: number;
  available_variant_count: number;
  price_min: string | null;
  price_max: string | null;
  primary_image_url: string | null;
  updated_at: string;
}

export interface Product {
  id: number;
  name: string;
  code: string;
  description: string;
  category: number;
  category_name: string;
  brand: string;
  status: ProductStatus;
  hsn_sac: string;
  weight: string | null;
  dimensions: string;
  tags: string[];
  notes: string;
  // optional default pricing — variants inherit these unless they override
  mrp: string | null;
  selling_price: string | null;
  purchase_price: string | null;
  tax_rate: string | null;
  discount_amount: string;
  discount_percent: string;
  variants: ProductVariant[];
  images: ProductImage[];
  created_at: string;
  updated_at: string;
}

export interface LabelSize {
  id: number;
  name: string;
  code: string;
  width_mm: string;
  height_mm: string;
  columns: number;
  rows: number;
  margin_mm: string;
  gutter_mm: string;
  orientation: "horizontal" | "vertical";
  is_active: boolean;
  is_default: boolean;
}
