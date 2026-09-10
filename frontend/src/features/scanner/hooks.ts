import { useQuery } from "@tanstack/react-query";

import { serializedUnitsApi } from "@/features/serialized-units/api";

/** Resolve a scanned/typed code against the Phase 3 lookup endpoint
 * (`GET /products/serialized-units/lookup/?code=`). The shared query client
 * already skips retries on 4xx, so a 404 (no match) / 403 (no `barcode.scan`)
 * surfaces immediately. */
export function useUnitLookup(code: string | null) {
  return useQuery({
    queryKey: ["scanner", "lookup", code],
    queryFn: () => serializedUnitsApi.lookup(code as string),
    enabled: Boolean(code),
    staleTime: 0,
    gcTime: 60_000,
  });
}
