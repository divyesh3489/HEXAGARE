import { api, apiRequest, type Paginated } from "@/api/client";
import type {
  AdminUser,
  AuditLogEntry,
  BackupJob,
  BusinessSettings,
  BusinessSettingsWriteBody,
  RolesMatrix,
  UserCreateBody,
  UserUpdateBody,
} from "./types";

const BASE = "/auth";

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export const businessSettingsApi = {
  get: () => api.get<BusinessSettings>(`${BASE}/settings/`),
  update: (body: BusinessSettingsWriteBody) =>
    api.patch<BusinessSettings>(`${BASE}/settings/`, body),
};

export interface UserQuery {
  [key: string]: string | number | undefined;
  page?: number;
  page_size?: number;
  search?: string;
  role?: string;
  is_active?: string;
}

export const usersApi = {
  list: (query: UserQuery = {}) => api.get<Paginated<AdminUser>>(`${BASE}/users/${qs(query)}`),
  create: (body: UserCreateBody) => api.post<AdminUser>(`${BASE}/users/`, body),
  update: (id: number, body: UserUpdateBody) =>
    api.patch<AdminUser>(`${BASE}/users/${id}/`, body),
  deactivate: (id: number) => api.post<AdminUser>(`${BASE}/users/${id}/deactivate/`),
  reactivate: (id: number) => api.post<AdminUser>(`${BASE}/users/${id}/reactivate/`),
};

export const rolesApi = {
  get: () => api.get<RolesMatrix>(`${BASE}/roles/`),
};

export interface AuditLogQuery {
  [key: string]: string | number | undefined;
  page?: number;
  page_size?: number;
  action?: string;
  actor?: number;
  object_type?: string;
  date_from?: string;
  date_to?: string;
}

export const auditLogApi = {
  list: (query: AuditLogQuery = {}) =>
    api.get<Paginated<AuditLogEntry>>(`${BASE}/audit-log/${qs(query)}`),
};

export interface BackupQuery {
  [key: string]: string | number | undefined;
  page?: number;
  page_size?: number;
}

export const backupsApi = {
  list: (query: BackupQuery = {}) => api.get<Paginated<BackupJob>>(`${BASE}/backups/${qs(query)}`),
  get: (id: number) => api.get<BackupJob>(`${BASE}/backups/${id}/`),
  create: () => api.post<BackupJob>(`${BASE}/backups/`),
  download: (id: number) =>
    apiRequest<Blob>(`${BASE}/backups/${id}/download/`, { method: "GET", parse: "blob" }),
};

export const settingsKeys = {
  businessSettings: ["settings", "business"] as const,
  users: (query: UserQuery) => ["settings", "users", query] as const,
  roles: ["settings", "roles"] as const,
  auditLog: (query: AuditLogQuery) => ["settings", "audit-log", query] as const,
  backups: (query: BackupQuery) => ["settings", "backups", query] as const,
  backup: (id: number) => ["settings", "backups", "detail", id] as const,
};
