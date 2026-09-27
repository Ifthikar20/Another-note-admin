import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, SessionEnded, api, errorMessage, query } from "./api";
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

  it("gives failures on our side a reference to look them up by", async () => {
    const rid = "1f0c2d9e-8b1a-4c3e-9f5d-2a7b6c4d8e10";
    const failing = (status: number, message: string) =>
      vi.fn(async () => new Response(JSON.stringify({ error: { code: "unavailable", message } }), { status, headers: { "x-request-id": rid } }));
    vi.stubGlobal("fetch", failing(502, "The admin API could not be reached."));
    const error = await api.get("/overview").catch((e: unknown) => e);
    expect(error).toMatchObject({ status: 502, requestId: rid });
    expect(errorMessage(error)).toBe("The admin API could not be reached. Reference 1f0c2d9e.");
    vi.stubGlobal("fetch", failing(400, "Give a reason."));
    expect(errorMessage(await api.post("/users/5/sign-out-everywhere", {}).catch((e: unknown) => e))).toBe("Give a reason.");
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
