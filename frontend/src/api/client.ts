import { useAuthStore } from "@/stores/auth";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

export interface ApiErrorBody {
  code: string;
  message: string;
  fields?: Record<string, string[]>;
}

/** Thrown for every non-2xx response. Carries the `{error: {...}}` envelope. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fields?: Record<string, string[]>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message || `Request failed (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.fields = body.fields;
  }

  /** First message for `field`, if the server reported one. */
  fieldError(field: string): string | undefined {
    return this.fields?.[field]?.[0];
  }
}

/** Standard list envelope produced by `apps.common.pagination.StandardPagination`. */
export interface Paginated<T> {
  data: T[];
  meta: { count: number; next: string | null; previous: string | null };
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** Attach the bearer token and attempt a refresh on 401. Default true. */
  auth?: boolean;
}

let refreshInFlight: Promise<string | null> | null = null;

async function runRefresh(): Promise<string | null> {
  const { refreshToken, setTokens, clearSession } = useAuthStore.getState();
  if (!refreshToken) return null;
  try {
    const response = await fetch(`${BASE_URL}/auth/refresh/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh: refreshToken }),
    });
    if (!response.ok) {
      clearSession();
      return null;
    }
    const data = (await response.json()) as { access: string; refresh?: string };
    setTokens({ access: data.access, refresh: data.refresh });
    return data.access;
  } catch {
    clearSession();
    return null;
  }
}

function ensureRefreshed(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = runRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, auth = true, headers, ...rest } = options;

  const send = async (): Promise<Response> => {
    const finalHeaders = new Headers(headers);
    const isFormData = body instanceof FormData;
    if (body !== undefined && !isFormData) {
      finalHeaders.set("Content-Type", "application/json");
    }
    if (auth) {
      const token = useAuthStore.getState().accessToken;
      if (token) finalHeaders.set("Authorization", `Bearer ${token}`);
    }
    return fetch(`${BASE_URL}${path}`, {
      ...rest,
      headers: finalHeaders,
      body:
        body === undefined ? undefined : isFormData ? (body as FormData) : JSON.stringify(body),
    });
  };

  let response = await send();

  if (response.status === 401 && auth && useAuthStore.getState().refreshToken) {
    const newToken = await ensureRefreshed();
    if (newToken) {
      response = await send();
    } else {
      throw new ApiError(401, {
        code: "session_expired",
        message: "Your session has expired. Please sign in again.",
      });
    }
  }

  if (response.status === 204 || response.status === 205) {
    return undefined as T;
  }

  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    const envelope: ApiErrorBody =
      payload && typeof payload === "object" && "error" in payload
        ? (payload as { error: ApiErrorBody }).error
        : { code: "error", message: `Request failed (${response.status})` };
    throw new ApiError(response.status, envelope);
  }

  return payload as T;
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: "POST", body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: "PATCH", body }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: "PUT", body }),
  delete: <T>(path: string, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: "DELETE" }),
};
