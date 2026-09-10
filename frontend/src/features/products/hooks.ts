import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  attributesApi,
  categoriesApi,
  imagesApi,
  productKeys,
  productsApi,
  variantsApi,
  type CategoryQuery,
  type ProductQuery,
} from "./api";

/* ----------------------------------------------------------------- Categories */

export function useCategories(query: CategoryQuery = {}) {
  return useQuery({
    queryKey: productKeys.categories(query),
    queryFn: () => categoriesApi.list(query),
    placeholderData: keepPreviousData,
  });
}

/** All categories, unpaginated-ish — for select inputs. */
export function useAllCategories() {
  return useQuery({
    queryKey: productKeys.categories({ page_size: 200 }),
    queryFn: () => categoriesApi.list({ page_size: 200 }),
  });
}

export function useCategoryMutations() {
  const qc = useQueryClient();
  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["products", "categories"] });
  return {
    create: useMutation({ mutationFn: categoriesApi.create, onSuccess: invalidate }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: number; body: Parameters<typeof categoriesApi.update>[1] }) =>
        categoriesApi.update(id, body),
      onSuccess: invalidate,
    }),
    remove: useMutation({ mutationFn: categoriesApi.remove, onSuccess: invalidate }),
  };
}

/* ------------------------------------------------------------------- Products */

export function useProducts(query: ProductQuery = {}) {
  return useQuery({
    queryKey: productKeys.products(query),
    queryFn: () => productsApi.list(query),
    placeholderData: keepPreviousData,
  });
}

export function useProduct(id: number | undefined) {
  return useQuery({
    queryKey: productKeys.product(id ?? -1),
    queryFn: () => productsApi.get(id as number),
    enabled: id !== undefined && id >= 0,
  });
}

export function useProductMutations() {
  const qc = useQueryClient();
  const invalidateLists = () => qc.invalidateQueries({ queryKey: ["products", "list"] });
  return {
    create: useMutation({ mutationFn: productsApi.create, onSuccess: invalidateLists }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: number; body: Parameters<typeof productsApi.update>[1] }) =>
        productsApi.update(id, body),
      onSuccess: (data) => {
        invalidateLists();
        qc.invalidateQueries({ queryKey: productKeys.product(data.id) });
      },
    }),
    remove: useMutation({ mutationFn: productsApi.remove, onSuccess: invalidateLists }),
  };
}

/* ------------------------------------------------------------------- Variants */

export function useVariants(productId: number) {
  return useQuery({
    queryKey: productKeys.variants(productId),
    queryFn: () => variantsApi.list(productId),
    enabled: productId >= 0,
  });
}

export function useVariantMutations(productId: number) {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: productKeys.variants(productId) });
    qc.invalidateQueries({ queryKey: productKeys.product(productId) });
    qc.invalidateQueries({ queryKey: ["products", "list"] });
  };
  return {
    create: useMutation({ mutationFn: variantsApi.create, onSuccess: invalidate }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: number; body: Parameters<typeof variantsApi.update>[1] }) =>
        variantsApi.update(id, body),
      onSuccess: invalidate,
    }),
    remove: useMutation({ mutationFn: variantsApi.remove, onSuccess: invalidate }),
  };
}

/* ----------------------------------------------------------------- Attributes */

export function useAttributes() {
  return useQuery({
    queryKey: productKeys.attributes(),
    queryFn: () => attributesApi.list(),
  });
}

export function useAttributeMutations() {
  const qc = useQueryClient();
  return {
    create: useMutation({
      mutationFn: attributesApi.create,
      onSuccess: () => qc.invalidateQueries({ queryKey: productKeys.attributes() }),
    }),
  };
}

/* --------------------------------------------------------------------- Images */

export function useImages(productId: number) {
  return useQuery({
    queryKey: productKeys.images(productId),
    queryFn: () => imagesApi.list(productId),
    enabled: productId >= 0,
  });
}

export function useImageMutations(productId: number) {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: productKeys.images(productId) });
    qc.invalidateQueries({ queryKey: productKeys.product(productId) });
    qc.invalidateQueries({ queryKey: ["products", "list"] });
  };
  return {
    upload: useMutation({ mutationFn: imagesApi.upload, onSuccess: invalidate }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: number; body: Parameters<typeof imagesApi.update>[1] }) =>
        imagesApi.update(id, body),
      onSuccess: invalidate,
    }),
    remove: useMutation({ mutationFn: imagesApi.remove, onSuccess: invalidate }),
  };
}
