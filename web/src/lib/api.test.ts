import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, SessionEnded, api, query } from "./api";
import { session } from "./session";

describe("the BFF client", () => {
  beforeEach(() => session.reset());
  afterEach(() => vi.unstubAllGlobals());

  it("sends X-Requested-With, never follows redirects, never caches", async () => {
    const fetch = vi.fn(async () => new Response('{"ok":true}', { status: 200, headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", fetch);
    await api.get("/users", { q: "a+b@example.com", kind: null, limit: 50 });
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/bff/users?q=a%2Bb%40example.com&limit=50");
    expect((init.headers as Record<string, string>)["X-Requested-With"]).toBe("admin");
    expect(init.redirect).toBe("manual");
    expect(init.cache).toBe("no-store");
    expect(init.credentials).toBe("same-origin");
  });

  it("turns the error envelope into an ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response('{"error":{"code":"forbidden","message":"Owners only."}}', { status: 403 })));
    const error = await api.get("/audit").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 403, code: "forbidden", message: "Owners only." });
  });

  it("ends the session on a 401", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 401 })));
    await expect(api.get("/me")).rejects.toBeInstanceOf(SessionEnded);
    expect(session.get()).toBe("ended");
  });

  it("ends the session when Cloudflare Access redirects to its sign-in page", async () => {
    const redirected = { ok: false, status: 0, type: "opaqueredirect", json: async () => ({}) } as unknown as Response;
    vi.stubGlobal("fetch", vi.fn(async () => redirected));
    await expect(api.post("/users/5/reveal-email", { reason: "because" })).rejects.toBeInstanceOf(SessionEnded);
    expect(session.get()).toBe("ended");
    session.unlock();
    expect(session.get()).toBe("ended"); // only a reload starts again
  });

  it("says so when the network is down", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    await expect(api.get("/me")).rejects.toMatchObject({ status: 0, code: "unavailable" });
  });

  it("leaves out empty query values", () => {
    expect(query({ a: "", b: undefined, c: null, d: 0, e: false })).toBe("?d=0&e=false");
    expect(query({})).toBe("");
  });
});
