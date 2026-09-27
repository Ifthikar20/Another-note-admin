/**
 * The only way the UI talks to anything: same-origin calls to the BFF under /bff.
 *
 * Every call carries X-Requested-With: admin (the BFF refuses calls without it, which a
 * cross-site page cannot add). Redirects are not followed: when the Cloudflare Access
 * session has ended, Cloudflare answers a call with a redirect to its sign-in page, and
 * following it would only produce a confusing CORS error. That, or a 401, ends the
 * session for the whole app (see session.ts).
 */
import { session } from "./session";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export class SessionEnded extends ApiError {
  constructor() {
    super(401, "unauthorized", "Your session ended. Reload the page to sign in again.");
    this.name = "SessionEnded";
  }
}

export type Params = Record<string, string | number | boolean | null | undefined>;

export function query(params?: Params): string {
  if (!params) return "";
  const pairs = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "");
  if (!pairs.length) return "";
  return "?" + pairs.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join("&");
}

export const BASE_HEADERS = { "X-Requested-With": "admin" } as const;

async function fail(res: Response): Promise<never> {
  if (res.type === "opaqueredirect" || res.status === 401) {
    session.end();
    throw new SessionEnded();
  }
  let code = "unavailable";
  let message = `The admin app answered ${res.status}.`;
  try {
    const body = await res.json();
    if (body && typeof body.error === "object" && body.error) {
      code = String(body.error.code ?? code);
      message = String(body.error.message ?? message);
    }
  } catch {
    /* not JSON: keep the generic message */
  }
  throw new ApiError(res.status, code, message);
}

export async function request<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/bff${path}`, {
      method,
      headers: {
        ...BASE_HEADERS,
        Accept: "application/json",
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      credentials: "same-origin",
      redirect: "manual",
      cache: "no-store",
      signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError(0, "unavailable", "Can't reach the admin app. Check your connection and try again.");
  }
  if (!res.ok || res.type === "opaqueredirect") return fail(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string, params?: Params, signal?: AbortSignal) => request<T>("GET", path + query(params), undefined, signal),
  post: <T>(path: string, body: unknown) => request<T>("POST", path, body),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
};

/** A file from the BFF (a CSV export), saved by the browser. */
export async function download(path: string, fallbackName: string): Promise<{ rows: number | null; truncated: boolean }> {
  let res: Response;
  try {
    res = await fetch(`/bff${path}`, { headers: BASE_HEADERS, credentials: "same-origin", redirect: "manual", cache: "no-store" });
  } catch {
    throw new ApiError(0, "unavailable", "Can't reach the admin app. Check your connection and try again.");
  }
  if (!res.ok || res.type === "opaqueredirect") return fail(res);
  const blob = await res.blob();
  const name = /filename="([^"]+)"/.exec(res.headers.get("content-disposition") ?? "")?.[1] ?? fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
  const rows = res.headers.get("x-export-rows");
  return { rows: rows ? Number(rows) : null, truncated: res.headers.get("x-export-truncated") === "1" };
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  return "Something went wrong. Try again.";
}
