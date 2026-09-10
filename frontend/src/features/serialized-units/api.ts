import { api, type Paginated } from "@/api/client";
import type { SerializedUnit } from "./types";

/** Phase 3 route; provisional until `apps/products` ships the endpoint. */
const ENDPOINT = "/products/serialized-units/";

export interface SerializedUnitQuery {
  page?: number;
  pageSize?: number;
  search?: string;
  status?: string;
}

export function fetchSerializedUnits(query: SerializedUnitQuery) {
  const params = new URLSearchParams();
  if (query.page) params.set("page", String(query.page));
  if (query.pageSize) params.set("page_size", String(query.pageSize));
  if (query.search) params.set("search", query.search);
  if (query.status) params.set("status", query.status);
  const qs = params.toString();
  return api.get<Paginated<SerializedUnit>>(`${ENDPOINT}${qs ? `?${qs}` : ""}`);
}

export const serializedUnitsKey = (query: SerializedUnitQuery) =>
  ["serialized-units", query] as const;
