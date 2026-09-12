import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  type AuditLogQuery,
  type BackupQuery,
  auditLogApi,
  backupsApi,
  businessSettingsApi,
  rolesApi,
  settingsKeys,
  type UserQuery,
  usersApi,
} from "./api";
import type { BusinessSettingsWriteBody, UserCreateBody, UserUpdateBody } from "./types";

export function useBusinessSettings() {
  return useQuery({
    queryKey: settingsKeys.businessSettings,
    queryFn: businessSettingsApi.get,
  });
}

export function useUpdateBusinessSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: BusinessSettingsWriteBody) => businessSettingsApi.update(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: settingsKeys.businessSettings }),
  });
}

export function useUsers(query: UserQuery = {}) {
  return useQuery({
    queryKey: settingsKeys.users(query),
    queryFn: () => usersApi.list(query),
    placeholderData: keepPreviousData,
  });
}

export function useUserMutations() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["settings", "users"] });
  return {
    create: useMutation({ mutationFn: (body: UserCreateBody) => usersApi.create(body), onSuccess: invalidate }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: number; body: UserUpdateBody }) => usersApi.update(id, body),
      onSuccess: invalidate,
    }),
    deactivate: useMutation({ mutationFn: usersApi.deactivate, onSuccess: invalidate }),
    reactivate: useMutation({ mutationFn: usersApi.reactivate, onSuccess: invalidate }),
  };
}

export function useRoles() {
  return useQuery({ queryKey: settingsKeys.roles, queryFn: rolesApi.get });
}

export function useAuditLog(query: AuditLogQuery = {}) {
  return useQuery({
    queryKey: settingsKeys.auditLog(query),
    queryFn: () => auditLogApi.list(query),
    placeholderData: keepPreviousData,
  });
}

export function useBackups(query: BackupQuery = {}) {
  return useQuery({
    queryKey: settingsKeys.backups(query),
    queryFn: () => backupsApi.list(query),
    placeholderData: keepPreviousData,
    // Keep the history fresh while any listed job is still in flight.
    refetchInterval: (q) =>
      (q.state.data?.data ?? []).some((b) => b.status === "PENDING" || b.status === "RUNNING")
        ? 2000
        : false,
  });
}

export function useCreateBackup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: backupsApi.create,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings", "backups"] }),
  });
}

/** Fetches the ready dump and saves it via a throwaway anchor element. */
export function useDownloadBackup() {
  return useMutation({
    mutationFn: async ({ id, filename }: { id: number; filename: string }) => {
      const blob = await backupsApi.download(id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    },
  });
}
