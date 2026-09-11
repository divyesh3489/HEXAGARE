import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  amazonFeeConfigApi,
  amazonImportsApi,
  amazonSkuMappingsApi,
  integrationsKeys,
  type ImportBatchQuery,
  type SkuMappingQuery,
} from "./api";

/* --------------------------------------------------------------------- Imports */

export function useImportBatches(query: ImportBatchQuery = {}) {
  return useQuery({
    queryKey: integrationsKeys.imports(query),
    queryFn: () => amazonImportsApi.list(query),
    placeholderData: keepPreviousData,
  });
}

/** One import batch. Polls every 2s while PENDING/PROCESSING -- same pattern
 * as the label-batch / invoice PDF poll. */
export function useImportBatch(id: number | undefined) {
  return useQuery({
    queryKey: integrationsKeys.import(id ?? -1),
    queryFn: () => amazonImportsApi.detail(id as number),
    enabled: id !== undefined && id >= 0,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "PENDING" || status === "PROCESSING" ? 2000 : false;
    },
  });
}

export function useUploadImport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => amazonImportsApi.upload(file),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["integrations", "amazon", "imports"] }),
  });
}

/* ----------------------------------------------------------------- SKU mapping */

export function useSkuMappings(query: SkuMappingQuery = {}) {
  return useQuery({
    queryKey: integrationsKeys.skuMappings(query),
    queryFn: () => amazonSkuMappingsApi.list(query),
    placeholderData: keepPreviousData,
  });
}

export function useSkuMappingMutations() {
  const qc = useQueryClient();
  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["integrations", "amazon", "sku-mappings"] });
  return {
    create: useMutation({ mutationFn: amazonSkuMappingsApi.create, onSuccess: invalidate }),
    update: useMutation({
      mutationFn: ({
        id,
        body,
      }: {
        id: number;
        body: Parameters<typeof amazonSkuMappingsApi.update>[1];
      }) => amazonSkuMappingsApi.update(id, body),
      onSuccess: invalidate,
    }),
    remove: useMutation({ mutationFn: amazonSkuMappingsApi.remove, onSuccess: invalidate }),
  };
}

/* ----------------------------------------------------------------- Fee config */

export function useFeeConfigs() {
  return useQuery({
    queryKey: integrationsKeys.feeConfigs(),
    queryFn: () => amazonFeeConfigApi.list(),
  });
}

export function useFeeConfigMutations() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: integrationsKeys.feeConfigs() });
  return {
    create: useMutation({ mutationFn: amazonFeeConfigApi.create, onSuccess: invalidate }),
    update: useMutation({
      mutationFn: ({
        id,
        body,
      }: {
        id: number;
        body: Parameters<typeof amazonFeeConfigApi.update>[1];
      }) => amazonFeeConfigApi.update(id, body),
      onSuccess: invalidate,
    }),
    remove: useMutation({ mutationFn: amazonFeeConfigApi.remove, onSuccess: invalidate }),
  };
}
