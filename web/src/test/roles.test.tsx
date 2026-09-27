/** What each role sees: navigation and the audited actions (5.8.3). */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/AppShell";
import { TooltipProvider } from "@/components/ui/tooltip";
import { MeContext } from "@/lib/me";
import type { Role } from "@/lib/types";
import UserDetail from "@/pages/UserDetail";

import { fakeFetch, me, userDetail } from "./fixtures";

function wrap(role: Role, path: string, routes: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MeContext.Provider value={me(role)}>
        <TooltipProvider>
          <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
            <Routes>{routes}</Routes>
          </MemoryRouter>
        </TooltipProvider>
      </MeContext.Provider>
    </QueryClientProvider>,
  );
}

const SECTIONS = ["Overview", "Users", "Tickets", "Activity", "Usage and cost", "Plans", "Organisations", "Security", "Audit log", "Settings"];
const VISIBLE: Record<Role, string[]> = {
  owner: SECTIONS,
  support: ["Overview", "Users", "Tickets", "Activity", "Usage and cost", "Plans", "Organisations", "Security"],
  analyst: ["Overview", "Users", "Activity", "Usage and cost", "Plans", "Organisations"],
  viewer: ["Overview", "Users", "Tickets", "Activity", "Usage and cost", "Plans", "Organisations"],
};

describe("navigation", () => {
  it.each(Object.keys(VISIBLE) as Role[])("shows %s only the sections the role may use", (role) => {
    wrap(role, "/", <Route element={<AppShell />}><Route path="/" element={<p>home</p>} /></Route>);
    const nav = screen.getByRole("navigation", { name: "Admin sections" });
    const shown = within(nav).getAllByRole("link").map((a) => a.textContent);
    expect(shown).toEqual(VISIBLE[role]);
  });

  it("offers sign-out through Cloudflare Access", () => {
    wrap("viewer", "/", <Route element={<AppShell />}><Route path="/" element={<p>home</p>} /></Route>);
    expect(screen.getByRole("button", { name: /sign out/i })).toBeInTheDocument();
  });
});

describe("a person's actions", () => {
  afterEach(() => vi.unstubAllGlobals());

  function person(role: Role, tab = "actions") {
    vi.stubGlobal(
      "fetch",
      fakeFetch({
        "GET /bff/users/481": userDetail(),
        "GET /bff/users/481/sessions": { items: [], next_cursor: null },
      }).fn,
    );
    return wrap(role, `/users/481?tab=${tab}`, <Route path="/users/:id" element={<UserDetail />} />);
  }

  it("lets an owner sign out, deactivate and change the plan", async () => {
    person("owner");
    expect(await screen.findByRole("button", { name: /sign out everywhere/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /deactivate/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Change plan" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reveal" })).toBeInTheDocument();
  });

  it("lets support sign out and reveal, but not deactivate or change plans", async () => {
    person("support");
    expect(await screen.findByRole("button", { name: /sign out everywhere/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /deactivate/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Change plan" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reveal" })).toBeInTheDocument();
  });

  it.each(["analyst", "viewer"] as const)("gives %s no actions at all", async (role) => {
    person(role, "activity");
    expect(await screen.findByText("Sam · #481")).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Actions" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Support" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "App activity" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reveal" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Change plan" })).not.toBeInTheDocument();
  });

  it("never shows anything but counts in the footprint", async () => {
    person("owner", "footprint");
    expect(await screen.findByText(/Study content is never shown in the admin app/)).toBeInTheDocument();
    expect(screen.getByText("Study sessions")).toBeInTheDocument();
    expect(screen.getByText("81.2 MB")).toBeInTheDocument();
  });
});
