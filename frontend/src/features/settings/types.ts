/** Shapes returned by `/api/v1/auth/{settings,users,roles,audit-log,backups}/`
 * (Phase 17 -- Administration). */

export interface BusinessSettings {
  business_name: string;
  address: string;
  phone: string;
  email: string;
  gstin: string;
  logo: string | null;
  currency: string;
  default_tax_rate: string | null;
  sku_prefix: string;
  serial_prefix: string;
  serial_padding: number | null;
  invoice_prefix: string;
  invoice_padding: number | null;
  updated_at: string;
  updated_by: string | null;
}

export interface BusinessSettingsWriteBody {
  business_name?: string;
  address?: string;
  phone?: string;
  email?: string;
  gstin?: string;
  currency?: string;
  default_tax_rate?: string | null;
  sku_prefix?: string;
  serial_prefix?: string;
  serial_padding?: string | number | null;
  invoice_prefix?: string;
  invoice_padding?: string | number | null;
}

export const ROLES = ["Admin", "Manager", "Cashier", "Warehouse"] as const;
export type Role = (typeof ROLES)[number];

export interface AdminUser {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  phone: string;
  is_active: boolean;
  role: Role | null;
  date_joined: string;
  last_login: string | null;
}

export interface UserCreateBody {
  email: string;
  password: string;
  first_name?: string;
  last_name?: string;
  phone?: string;
  role: Role;
}

export interface UserUpdateBody {
  first_name?: string;
  last_name?: string;
  phone?: string;
  role?: Role;
}

export interface RolePermissions {
  role: string;
  permissions: string[];
}

export interface PermissionInfo {
  codename: string;
  name: string;
}

export interface RolesMatrix {
  roles: RolePermissions[];
  permissions: PermissionInfo[];
}

export interface AuditLogEntry {
  id: number;
  actor: number | null;
  actor_email: string | null;
  action: string;
  object_type: string | null;
  object_id: string;
  object_repr: string;
  changes: Record<string, { old: unknown; new: unknown }>;
  ip_address: string | null;
  created_at: string;
}

export type BackupStatus = "PENDING" | "RUNNING" | "SUCCESS" | "FAILED";

export interface BackupJob {
  id: number;
  status: BackupStatus;
  file_size: number | null;
  error_message: string;
  triggered_by_email: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}
