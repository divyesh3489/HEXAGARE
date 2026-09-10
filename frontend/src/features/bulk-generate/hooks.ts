import { useEffect, useState } from "react";
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import {
  labelBatchKeys,
  labelBatchLocationsApi,
  labelBatchesApi,
  labelSizesApi,
  type LabelBatchQuery,
} from "./api";

export function useLabelBatches(query: LabelBatchQuery = {}) {
  return useQuery({
    queryKey: labelBatchKeys.list(query),
    queryFn: () => labelBatchesApi.list(query),
    placeholderData: keepPreviousData,
  });
}

/** One batch. While the PDF is still rendering, poll every 2s. */
export function useLabelBatch(id: number | undefined) {
  return useQuery({
    queryKey: labelBatchKeys.detail(id ?? -1),
    queryFn: () => labelBatchesApi.get(id as number),
    enabled: id !== undefined && id >= 0,
    refetchInterval: (query) =>
      query.state.data?.status === "PENDING" ? 2000 : false,
  });
}

export function useLabelSizes() {
  return useQuery({
    queryKey: labelBatchKeys.labelSizes(),
    queryFn: () => labelSizesApi.list(),
    staleTime: 5 * 60 * 1000,
  });
}

export function useLabelBatchLocations() {
  return useQuery({
    queryKey: labelBatchKeys.locations(),
    queryFn: () => labelBatchLocationsApi.list(),
    staleTime: 5 * 60 * 1000,
  });
}

export function useNextSerial(variantId: number | undefined) {
  return useQuery({
    queryKey: labelBatchKeys.nextSerial(variantId ?? -1),
    queryFn: () => labelBatchesApi.nextSerial(variantId as number),
    enabled: variantId !== undefined && variantId >= 0,
  });
}

export function useLabelBatchMutations() {
  const qc = useQueryClient();
  const invalidate = (id?: number) => {
    qc.invalidateQueries({ queryKey: ["label-batches", "list"] });
    if (id !== undefined) {
      qc.invalidateQueries({ queryKey: labelBatchKeys.detail(id) });
      qc.invalidateQueries({ queryKey: labelBatchKeys.pdf(id) });
    }
  };
  return {
    create: useMutation({
      mutationFn: labelBatchesApi.create,
      onSuccess: (batch) => invalidate(batch.id),
    }),
    regenerate: useMutation({
      mutationFn: labelBatchesApi.regenerate,
      onSuccess: (batch) => invalidate(batch.id),
    }),
  };
}

/** Fetches the rendered PDF and exposes it as an object URL, revoking the
 * previous one on change/unmount. Only runs once the batch is READY. */
export function useLabelBatchPdf(id: number | undefined, ready: boolean) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const query = useQuery({
    queryKey: labelBatchKeys.pdf(id ?? -1),
    queryFn: () => labelBatchesApi.pdf(id as number),
    enabled: id !== undefined && id >= 0 && ready,
    staleTime: Infinity,
  });

  useEffect(() => {
    if (!query.data) {
      setObjectUrl(null);
      return;
    }
    const url = URL.createObjectURL(query.data);
    setObjectUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [query.data]);

  return { ...query, objectUrl };
}
