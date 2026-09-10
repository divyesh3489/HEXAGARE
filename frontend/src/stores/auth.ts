import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface AuthUser {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  phone: string;
  is_active: boolean;
  is_staff: boolean;
  is_superuser: boolean;
  roles: string[];
  permissions: string[];
  date_joined: string;
  last_login: string | null;
}

interface SessionPayload {
  access: string;
  refresh: string;
  user: AuthUser;
}

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: AuthUser | null;
  setSession: (payload: SessionPayload) => void;
  setTokens: (tokens: { access: string; refresh?: string }) => void;
  setUser: (user: AuthUser) => void;
  clearSession: () => void;
}

/**
 * The single source of truth for auth state. Persisted to localStorage so a
 * refresh keeps the session; the fetch client reads it non-reactively via
 * `useAuthStore.getState()`.
 */
export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      setSession: ({ access, refresh, user }) =>
        set({ accessToken: access, refreshToken: refresh, user }),
      setTokens: ({ access, refresh }) =>
        set((state) => ({
          accessToken: access,
          refreshToken: refresh ?? state.refreshToken,
        })),
      setUser: (user) => set({ user }),
      clearSession: () => set({ accessToken: null, refreshToken: null, user: null }),
    }),
    { name: "hexagare.auth" },
  ),
);
