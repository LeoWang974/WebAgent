/**
 * File purpose: Implements browser-side API access for api client.
 * Main declarations: ApiError defines api error state or behavior; getAccessToken handles get
 * access token; apiClient handles api client; API_BASE_URL exposes the api base url public API.
 */

export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export interface ApiClientInit extends RequestInit {
  timeoutMs?: number;
}

export function getAccessToken() {
  if (typeof window === "undefined") {
    return undefined;
  }

  return window.localStorage.getItem("webagent_access_token") ?? undefined;
}

export async function apiClient<T>(
  path: string,
  init?: ApiClientInit,
): Promise<T> {
  const { timeoutMs = 60_000, ...requestInit } = init ?? {};
  const headers = new Headers(requestInit.headers);
  const token = getAccessToken();

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  if (!(requestInit.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const controller = new AbortController();
  const timeoutId = globalThis.setTimeout(() => controller.abort(), timeoutMs);
  const forwardAbort = () => controller.abort();
  if (requestInit.signal?.aborted) {
    controller.abort();
  }
  requestInit.signal?.addEventListener("abort", forwardAbort, { once: true });

  let response!: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...requestInit,
      headers,
      signal: controller.signal,
    });
  } finally {
    globalThis.clearTimeout(timeoutId);
    requestInit.signal?.removeEventListener("abort", forwardAbort);
  }

  if (!response.ok) {
    let detail = `API request failed: ${response.status}`;
    try {
      const payload = await response.json();
      if (typeof payload.detail === "string") {
        detail = payload.detail;
      }
    } catch {
      // Keep the generic status message when the backend returns a non-JSON error.
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("Content-Type") ?? "";

  if (!contentType.includes("application/json")) {
    return response.blob() as Promise<T>;
  }

  return response.json() as Promise<T>;
}
