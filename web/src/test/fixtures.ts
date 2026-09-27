import type { Me, Role, UserDetail } from "@/lib/types";

const CAPABILITIES: Record<Role, string[]> = {
  owner: [
    "activity.read", "audit.read", "metrics.read", "orgs.read", "plans.read", "plans.write", "security.read", "settings.read",
    "tickets.events", "tickets.read", "tickets.write", "users.auth_events", "users.read", "users.reveal_email", "users.set_active",
    "users.sign_out", "users.tickets",
  ],
  support: [
    "activity.read", "metrics.read", "orgs.read", "plans.read", "security.read", "tickets.events", "tickets.read", "tickets.write",
    "users.auth_events", "users.read", "users.reveal_email", "users.sign_out", "users.tickets",
  ],
  analyst: ["metrics.read", "orgs.read", "plans.read", "users.read"],
  viewer: ["metrics.read", "orgs.read", "plans.read", "tickets.read", "users.read"],
};

export function me(role: Role): Me {
  return {
    email: `${role}@anothernote.app`,
    role,
    capabilities: CAPABILITIES[role],
    environment: "production",
    dev_identity: false,
    version: "test",
    sign_out_url: "/cdn-cgi/access/logout",
    idle_lock_minutes: 15,
    idle_sign_out_minutes: 60,
  };
}

export function userDetail(overrides: Partial<UserDetail["user"]> = {}): UserDetail {
  return {
    user: {
      id: 481,
      identity: { email_masked: "s***@lincoln.edu", username_masked: null, first_name: "Sam" },
      kind: "standard",
      role: "student",
      age_band: "13_17",
      organization: { id: 7, name: "Lincoln High" },
      plan: { id: "school", name: "School", source: "organization", status: "active" },
      created_at: "2026-09-02T10:11:00Z",
      last_login: "2026-10-31T08:02:00Z",
      last_seen_at: "2026-10-31T13:59:00Z",
      live_sessions: 2,
      usage_30d: { tokens: 1840022, cost_usd: 4.12 },
      open_tickets: 1,
      status: "active",
      flags: ["child_linked"],
      ...overrides,
    },
    profile: {
      auth_provider: "google",
      org_role: "member",
      onboarding_completed: true,
      credentials_locked: false,
      pin_locked_until: null,
      xp: 3200,
      deleted_at: null,
      is_demo: false,
      email_domain: "lincoln.edu",
    },
    footprint: {
      study_sessions: 14, notes: 22, youtube_sessions: 3, pdfs: 9, office_files: 2, pdf_bytes: 81233455,
      highlights: 130, sticky_notes: 12, answers: 944, last_session_at: "2026-10-30T19:40:00Z",
    },
    family: { guardians_active: 1, guardians_revoked: 0, children_active: 0, children_revoked: 0, links: [] },
    security: { failed_sign_ins_30d: 0, locked_until: null, replays_30d: 0 },
    usage_by_feature_30d: [{ feature: "teach.script", tokens: 900233, cost_usd: 2.2 }],
    activity_30d: [{ day: "2026-10-31", active_seconds: 1800 }],
    note: "Study content is never shown in the admin app.",
  };
}

/** A fetch that answers from a table of (method path) → JSON, and records every call. */
export function fakeFetch(routes: Record<string, unknown | ((init: RequestInit | undefined) => unknown)>) {
  const calls: { url: string; init: RequestInit | undefined }[] = [];
  const fn = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    calls.push({ url, init });
    const key = `${(init?.method ?? "GET").toUpperCase()} ${url.split("?")[0]}`;
    const route = routes[key];
    if (route === undefined) return new Response(JSON.stringify({ error: { code: "not_found", message: `no fake for ${key}` } }), { status: 404 });
    const body = typeof route === "function" ? (route as (i: RequestInit | undefined) => unknown)(init) : route;
    return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
  };
  return { fn, calls };
}
