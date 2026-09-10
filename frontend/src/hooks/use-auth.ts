import { useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import * as authApi from "@/api/auth";
import { useAuthStore } from "@/stores/auth";

export function useCurrentUser() {
  return useAuthStore((s) => s.user);
}

export function useIsAuthenticated() {
  return useAuthStore((s) => Boolean(s.accessToken));
}

/** `(codename) => boolean` against the current user's resolved permissions. */
export function useHasPermission() {
  const user = useAuthStore((s) => s.user);
  return useCallback(
    (codename: string) =>
      Boolean(user && (user.is_superuser || user.permissions.includes(codename))),
    [user],
  );
}

export function useLogin() {
  const setSession = useAuthStore((s) => s.setSession);
  return useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      authApi.login(email, password),
    onSuccess: (data) =>
      setSession({ access: data.access, refresh: data.refresh, user: data.user }),
  });
}

export function useLogout() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const refresh = useAuthStore.getState().refreshToken;
      if (refresh) {
        try {
          await authApi.logout(refresh);
        } catch {
          // A failed blacklist call still clears the local session below.
        }
      }
    },
    onSettled: () => {
      useAuthStore.getState().clearSession();
      queryClient.clear();
      navigate("/login", { replace: true });
    },
  });
}

/** Fetches the profile and refreshes the cached user (roles/permissions). */
export function useProfile() {
  const setUser = useAuthStore((s) => s.setUser);
  const enabled = useIsAuthenticated();
  return useQuery({
    queryKey: ["profile"],
    queryFn: async () => {
      const user = await authApi.fetchProfile();
      setUser(user);
      return user;
    },
    enabled,
  });
}
