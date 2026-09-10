import { useEffect, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import {
  locationsApi,
  serializedUnitKeys,
  serializedUnitsApi,
  type SerializedUnitQuery,
} from "./api";

export function useSerializedUnits(query: SerializedUnitQuery) {
  return useQuery({
    queryKey: serializedUnitKeys.list(query),
    queryFn: () => serializedUnitsApi.list(query),
    placeholderData: keepPreviousData,
  });
}

export function useSerializedUnit(id: number | undefined) {
  return useQuery({
    queryKey: serializedUnitKeys.detail(id ?? -1),
    queryFn: () => serializedUnitsApi.get(id as number),
    enabled: id !== undefined && id >= 0,
  });
}

export function useLocations() {
  return useQuery({
    queryKey: serializedUnitKeys.locations(),
    queryFn: () => locationsApi.list(),
    staleTime: 5 * 60 * 1000,
  });
}

/** Fetches the on-demand barcode PNG and exposes it as an object URL,
 * revoking the previous one on change/unmount. */
export function useUnitBarcode(id: number | undefined) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const query = useQuery({
    queryKey: serializedUnitKeys.barcode(id ?? -1),
    queryFn: () => serializedUnitsApi.barcode(id as number),
    enabled: id !== undefined && id >= 0,
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

/** Debounces a raw text input by `delay` ms. */
export function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const handle = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(handle);
  }, [value, delay]);
  return debounced;
}
