import { api, apiRequest, type Paginated } from "@/api/client";
import type {
  Category,
  Product,
  ProductAttribute,
  ProductImage,
  ProductListItem,
  ProductVariant,
} from "./types";

const BASE = "/products";

function qs(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

/* ------------------------------------------------------------------ Categories */

export interface CategoryQuery {
  [key: string]: string | number | undefined;
  page?: number;
  page_size?: number;
  search?: string;
  parent?: string;
}

export const categoriesApi = {
  list: (query: CategoryQuery = {}) =>
    api.get<Paginated<Category>>(`${BASE}/categories/${qs(query)}`),
  create: (body: Partial<Category>) => api.post<Category>(`${BASE}/categories/`, body),
  update: (id: number, body: Partial<Category>) =>
    api.patch<Category>(`${BASE}/categories/${id}/`, body),
  remove: (id: number) => api.delete<void>(`${BASE}/categories/${id}/`),
};

/* -------------------------------------------------------------------- Products */

export interface ProductQuery {
  [key: string]: string | number | undefined;
  page?: number;
  page_size?: number;
  search?: string;
  category?: string;
  status?: string;
  brand?: string;
  ordering?: string;
}

export const productsApi = {
  list: (query: ProductQuery = {}) =>
    api.get<Paginated<ProductListItem>>(`${BASE}/${qs(query)}`),
  get: (id: number) => api.get<Product>(`${BASE}/${id}/`),
  create: (body: Partial<Product>) => api.post<Product>(`${BASE}/`, body),
  update: (id: number, body: Partial<Product>) => api.patch<Product>(`${BASE}/${id}/`, body),
  remove: (id: number) => api.delete<void>(`${BASE}/${id}/`),
};

/* -------------------------------------------------------------------- Variants */

export const variantsApi = {
  list: (productId: number) =>
    api.get<Paginated<ProductVariant>>(`${BASE}/variants/${qs({ product: productId, page_size: 100 })}`),
  /** Free-text search over sku/name/barcode, restricted to sellable variants
   * (`?available=1`) — used by the POS product-search add. */
  search: (search: string) =>
    api.get<Paginated<ProductVariant>>(
      `${BASE}/variants/${qs({ search, available: 1, page_size: 10 })}`,
    ),
  /** Free-text search over every variant regardless of active status --
   * used by Purchase Order line entry, where restocking a not-yet-active
   * or discontinued variant is still valid. */
  searchAll: (search: string) =>
    api.get<Paginated<ProductVariant>>(`${BASE}/variants/${qs({ search, page_size: 10 })}`),
  create: (body: Partial<ProductVariant>) =>
    api.post<ProductVariant>(`${BASE}/variants/`, body),
  update: (id: number, body: Partial<ProductVariant>) =>
    api.patch<ProductVariant>(`${BASE}/variants/${id}/`, body),
  remove: (id: number) => api.delete<void>(`${BASE}/variants/${id}/`),
};

/* ------------------------------------------------------------------ Attributes */

export const attributesApi = {
  list: () =>
    api.get<Paginated<ProductAttribute>>(`${BASE}/attributes/${qs({ page_size: 100 })}`),
  create: (body: Partial<ProductAttribute>) =>
    api.post<ProductAttribute>(`${BASE}/attributes/`, body),
};

/* ---------------------------------------------------------------------- Images */

export const imagesApi = {
  list: (productId: number) =>
    api.get<Paginated<ProductImage>>(`${BASE}/images/${qs({ product: productId, page_size: 100 })}`),
  upload: (input: {
    product: number;
    variant?: number | null;
    image: File;
    alt_text?: string;
    is_primary?: boolean;
  }) => {
    const form = new FormData();
    form.append("product", String(input.product));
    if (input.variant) form.append("variant", String(input.variant));
    form.append("image", input.image);
    if (input.alt_text) form.append("alt_text", input.alt_text);
    if (input.is_primary) form.append("is_primary", "true");
    return apiRequest<ProductImage>(`${BASE}/images/`, { method: "POST", body: form });
  },
  update: (id: number, body: Partial<ProductImage>) =>
    api.patch<ProductImage>(`${BASE}/images/${id}/`, body),
  remove: (id: number) => api.delete<void>(`${BASE}/images/${id}/`),
};

/* ------------------------------------------------------------------------- SKU */

export const skuApi = {
  suggest: (body: {
    category?: number | null;
    product?: number | null;
    variant_code?: string;
    attribute_values?: string[];
  }) => api.post<{ sku: string }>(`${BASE}/sku/suggest/`, body),
  check: (sku: string, excludeVariant?: number) =>
    api.get<{ sku: string; available: boolean }>(
      `${BASE}/sku/check/${qs({ sku, exclude_variant: excludeVariant })}`,
    ),
};

/* ------------------------------------------------------------------- Query keys */

export const productKeys = {
  categories: (query?: CategoryQuery) => ["products", "categories", query ?? {}] as const,
  products: (query?: ProductQuery) => ["products", "list", query ?? {}] as const,
  product: (id: number) => ["products", "detail", id] as const,
  variants: (productId: number) => ["products", "variants", productId] as const,
  attributes: () => ["products", "attributes"] as const,
  images: (productId: number) => ["products", "images", productId] as const,
};
