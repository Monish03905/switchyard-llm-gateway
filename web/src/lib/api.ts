const ADMIN_STORAGE = "switchyard-admin-token";

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").trim().replace(/\/+$/, "");

export function apiUrl(path: string): string {
  if (!API_BASE || /^https?:\/\//i.test(path)) return path;
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

export class ApiError extends Error {
  status: number;
  code: string | number | undefined;
  details: unknown;

  constructor(message: string, status: number, code?: string | number, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function getAdminToken(): string {
  try {
    return sessionStorage.getItem(ADMIN_STORAGE) ?? "";
  } catch {
    return "";
  }
}

export function setAdminToken(token: string): void {
  try {
    if (token) sessionStorage.setItem(ADMIN_STORAGE, token);
    else sessionStorage.removeItem(ADMIN_STORAGE);
  } catch {
    /* storage can be denied; the token simply will not persist */
  }
}

type RequestOptions = {
  method?: string;
  body?: unknown;
  admin?: boolean;
  signal?: AbortSignal;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (options.admin) {
    const token = getAdminToken();
    if (token) headers["X-Admin-Token"] = token;
  }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 120_000);
  if (options.signal) {
    options.signal.addEventListener("abort", () => controller.abort(), { once: true });
  }
  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: controller.signal,
    });
  } catch (error) {
    clearTimeout(timeout);
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("The yard did not answer in time. Check the server log.", 0, "timeout");
    }
    throw new ApiError(
      API_BASE
        ? `Cannot reach the API at ${API_BASE}. Is the backend running?`
        : "Cannot reach the yard. Is the API running on this origin?",
      0,
      "network",
    );
  }
  clearTimeout(timeout);

  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("text/html")) {
    throw new ApiError(
      API_BASE
        ? `The API at ${API_BASE} returned a web page instead of JSON. Check that the backend is running.`
        : "This cockpit is not connected to the API. Set VITE_API_BASE_URL to the FastAPI origin and redeploy.",
      response.status,
      "api_not_connected",
    );
  }

  let payload: unknown = null;
  const text = await response.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!response.ok) {
    const error = (payload as { error?: { message?: string; code?: string | number; details?: unknown } })?.error;
    const message =
      error?.message ??
      (typeof payload === "string" && payload ? payload : `Request failed (${response.status})`);
    throw new ApiError(message, response.status, error?.code, error?.details);
  }
  return payload as T;
}

export const api = {
  get<T>(path: string, options: { admin?: boolean; signal?: AbortSignal } = {}): Promise<T> {
    return request<T>(path, options);
  },
  post<T>(path: string, body?: unknown, options: { admin?: boolean } = {}): Promise<T> {
    return request<T>(path, { method: "POST", body: body ?? {}, ...options });
  },
  del<T>(path: string, options: { admin?: boolean } = {}): Promise<T> {
    return request<T>(path, { method: "DELETE", ...options });
  },
  adminToken: { get: getAdminToken, set: setAdminToken },
};

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  return "Something went sideways in the yard.";
}

export function isUnauthorized(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}
