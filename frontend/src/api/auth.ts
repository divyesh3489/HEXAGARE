import { api } from "./client";
import type { AuthUser } from "@/stores/auth";

export interface LoginResponse {
  access: string;
  refresh: string;
  user: AuthUser;
}

export const login = (email: string, password: string) =>
  api.post<LoginResponse>("/auth/login/", { email, password }, { auth: false });

export const logout = (refresh: string) => api.post<void>("/auth/logout/", { refresh });

export const fetchProfile = () => api.get<AuthUser>("/auth/profile/");

export type ProfilePatch = Partial<
  Pick<AuthUser, "first_name" | "last_name" | "phone" | "email">
>;

export const updateProfile = (patch: ProfilePatch) =>
  api.patch<AuthUser>("/auth/profile/", patch);

export const changePassword = (payload: { old_password: string; new_password: string }) =>
  api.post<{ detail: string }>("/auth/password/change/", payload);

export const requestPasswordReset = (email: string) =>
  api.post<{ detail: string }>("/auth/password/reset/", { email }, { auth: false });

export const confirmPasswordReset = (payload: {
  uid: string;
  token: string;
  new_password: string;
}) => api.post<{ detail: string }>("/auth/password/reset/confirm/", payload, { auth: false });
